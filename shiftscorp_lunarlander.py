# !pip install gymnasium
# !pip install "gymnasium[atari, accept-rom-license]"
# !apt-get install -y swig
# !pip install gymnasium[box2d]

import os
import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.autograd as autograd
from torch.autograd import Variable
from collections import deque, namedtuple

class Network(nn.Module):
  def __init__(self, state_size, action_size,seed=42) -> None:
      super(Network, self).__init__()
      self.seed = torch.manual_seed(seed)
      self.fc1 = nn.Linear(state_size, 64)
      self.fc2 = nn.Linear(64, 64)
      self.fc3 = nn.Linear(64,action_size)

  def forward(self,state):
    x = self.fc1(state)
    x = F.relu(x)
    x = self.fc2(x)
    x = F.relu(x)
    return self.fc3(x)

import gymnasium as gym
env = gym.make('LunarLander-v3')
state_shape = env.observation_space.shape
state_size = env.observation_space.shape[0]
number_actions = env.action_space.n
print('State shape: ', state_shape)
print('State size: ', state_size)
print('Number of actions: ', number_actions)
learning_rate = 5e-4
minibatch_size = 100
discount_factor = 0.99
replay_bufer_size = int(1e5)
interpolation_param = 1e-3

class ReplayMemory(object):

  def __init__(self, capacity):
    self.device = torch.device("cude:0" if torch.cuda.is_available() else "cpu")
    self.capacity = capacity
    self.memory = []

  def push(self, event):
    self.memory.append(event)
    if len(self.memory) > self.capacity:
      del self.memory[0]

  def sample(self, batch_size):
    exps = random.sample(self.memory, k = batch_size)
    states  = torch.from_numpy(np.vstack([e[0] for e in exps if e is not None])).float().to(self.device)
    actions  = torch.from_numpy(np.vstack([e[1] for e in exps if e is not None])).long().to(self.device)
    rewards  = torch.from_numpy(np.vstack([e[2] for e in exps if e is not None])).float().to(self.device)
    next_states  = torch.from_numpy(np.vstack([e[3] for e in exps if e is not None])).float().to(self.device)
    dones  = torch.from_numpy(np.vstack([e[4] for e in exps if e is not None]).astype(np.uint8)).float().to(self.device)
    return states, next_states, actions, rewards, dones

from threading import local
class Buddy():
  def __init__(self, state_size, action_size):
    self.device = torch.device("cude:0" if torch.cuda.is_available() else "cpu")
    self.state_size = state_size
    self.action_size = action_size
    self.local_qnet = Network(state_size, action_size).to(self.device)
    self.target_qnet = Network(state_size, action_size).to(self.device)
    self.optimizer = optim.Adam(self.local_qnet.parameters(), lr = learning_rate)
    self.memory = ReplayMemory(replay_bufer_size)
    self.t_step = 0

  def step(self, state, action, reward, next_state, done):
    self.memory.push((state, action, reward, next_state, done))
    self.t_step = (self.t_step + 1) % 4
    if self.t_step == 0:
      if len(self.memory.memory) > minibatch_size:
        experiences = self.memory.sample(100)
        self.learn(experiences, discount_factor)

  def act(self, state, epsilon = 0.):
    state = torch.from_numpy(state).float().unsqueeze(0).to(self.device)
    self.local_qnet.eval()
    with torch.no_grad():
      action_values = self.local_qnet(state)
    self.local_qnet.train()
    if random.random() > epsilon:
      return np.argmax(action_values.cpu().data.numpy())
    else:
      return random.choice(np.arange(self.action_size))

  def learn(self, experiences, discount_factor):
    states, next_states, actions, rewards, dones = experiences
    next_q_targets = self.target_qnet(next_states).detach().max(1)[0].unsqueeze(1)
    q_targets = rewards + (discount_factor * next_q_targets * (1-dones))
    q_expected = self.local_qnet(states).gather(1, actions)
    loss = F.mse_loss(q_expected, q_targets)
    self.optimizer.zero_grad()
    loss.backward()
    self.optimizer.step()
    self.soft_update(self.local_qnet, self.target_qnet, interpolation_param)

  def soft_update(self, local_model, target_model, interpolation_param):
    for target_param, local_param in zip(target_model.parameters(), local_model.parameters()):
      target_param.data.copy_(interpolation_param * local_param.data + (1.0 - interpolation_param) * target_param.data)

agent = Buddy(state_size, number_actions)

number_episodes = 2000
maximum_num_steps_per_ep = 1000
epsilon_start_val = 1.0
epsilon_end_val = 0.01
epsilon_decay_val = 0.995
epsilon = epsilon_start_val
scores_on100_ep = deque(maxlen = 100)

for episode in range(1,number_episodes + 1):
  state, _ = env.reset()
  score = 0
  for t in range(maximum_num_steps_per_ep):
    action = agent.act(state, epsilon)
    next_state, reward, done, _, _ = env.step(action)
    agent.step(state, action, reward, next_state, done)
    state = next_state
    score += reward
    if done:
      break
  scores_on100_ep.append(score)
  epsilon = max(epsilon_end_val, epsilon_decay_val * epsilon)
  print('\rEpisode {}\tAverage Score: {:.2f}'.format(episode, np.mean(scores_on100_ep)), end = "")
  if episode % 100 == 0:
     print('\rEpisode {}\tAverage Score: {:.2f}'.format(episode, np.mean(scores_on100_ep)))
  if np.mean(scores_on100_ep) >= 200.0:
     print('\nEnvironment solved in {:d} episodes!\Average Score: {:.2f}'.format(episode, np.mean(scores_on100_ep)))
     torch.save(agent.local_qnet.state_dict(), 'checkpoint.pth')
     break

import glob
import io
import base64
import imageio
from IPython.display import HTML, display

def show_video_of_model(agent, env_name):
    env = gym.make(env_name, render_mode='rgb_array')
    state, _ = env.reset()
    done = False
    frames = []
    while not done:
        frame = env.render()
        frames.append(frame)
        action = agent.act(state)
        state, reward, done, _, _ = env.step(action.item())
    env.close()
    imageio.mimsave('video.mp4', frames, fps=30)

show_video_of_model(agent, 'LunarLander-v3')

def show_video():
    mp4list = glob.glob('*.mp4')
    if len(mp4list) > 0:
        mp4 = mp4list[0]
        video = io.open(mp4, 'r+b').read()
        encoded = base64.b64encode(video)
        display(HTML(data='''<video alt="test" autoplay
                loop controls style="height: 400px;">
                <source src="data:video/mp4;base64,{0}" type="video/mp4" />
             </video>'''.format(encoded.decode('ascii'))))
    else:
        print("Could not find video")

show_video()
