import numpy as np

from social_dilemmas.envs.agent import HarvestAgent
from social_dilemmas.constants import HARVEST_MAP
from social_dilemmas.envs.map_env import MapEnv

APPLE_RADIUS = 2

COLOURS = {' ': [0, 0, 0],  # Black background
           '': [195, 0, 255],  # Board walls
           '@': [195, 0, 255],  # Board walls
           'A': [0, 255, 0],  # Green apples
           'P': [0, 255, 255],  # Player #FIXME(ev) agents need to have different colors
           'F': [255, 255, 0]}  # Yellow firing beam

# the axes look like
# graphic is here to help me get my head in order
# WARNING: increasing array position in the direction of down
# so for example if you move_left when facing left
# your y position decreases.
#         ^
#         |
#         U
#         P
# <--LEFT*RIGHT---->
#         D
#         O
#         W
#         N
#         |

# Currently on the display though we are off by 90 degrees

# FIXME(EV) the axes are 10000000% rotated oddly
# use keyword names so that it's easy to understand what the agent is calling
ACTIONS = {'MOVE_LEFT': [-1, 0],  # Move left
           'MOVE_RIGHT': [1, 0],  # Move right
           'MOVE_UP': [0, -1],  # Move up
           'MOVE_DOWN': [0, 1],  # Move down
           'STAY': [0, 0],  # don't move
           'TURN_CLOCKWISE': [[0, -1], [1, 0]],  # Rotate counter clockwise
           'TURN_COUNTERCLOCKWISE': [[0, 1], [-1, 0]],  # Move right
           'FIRE': 5}  # Fire 5 squares forward #FIXME(ev) is the firing in a straight line?

SPAWN_PROB = [0, 0.005, 0.02, 0.05]

ORIENTATIONS = {'LEFT': [-1, 0],
                'RIGHT': [1, 0],
                'UP': [0, -1],
                'DOWN': [0, 1]}


# FIXME(ev) this whole thing is in serious need of some abstraction
# FIXME(ev) switching betewen types and lists in a pretty arbitrary manner


class HarvestEnv(MapEnv):

    def __init__(self, ascii_map=HARVEST_MAP, num_agents=1, render=False):
        super().__init__(ascii_map, COLOURS, num_agents, render)
        # set up the list of spawn points
        self.spawn_points = []
        self.apple_points = []
        self.wall_points = []
        self.firing_points = []
        self.hidden_apples = []
        for row in range(self.base_map.shape[0]):
            for col in range(self.base_map.shape[1]):
                if self.base_map[row, col] == 'P':
                    self.spawn_points.append([row, col])
                elif self.base_map[row, col] == 'A':
                    self.apple_points.append([row, col])
                elif self.base_map[row, col] == '@':
                    self.wall_points.append([row, col])
        # TODO(ev) this call should be in the superclass
        self.setup_agents()

    # FIXME(ev) action_space should really be defined in the agents
    @property
    def action_space(self):
        pass

    @property
    def observation_space(self):
        pass

    # TODO(ev) this can probably be moved into the superclass
    def setup_agents(self):
        for i in range(self.num_agents):
            agent_id = 'agent-' + str(i)
            agent = HarvestAgent(agent_id, self.spawn_point(), self.spawn_rotation(), self, 3)
            self.agents[agent_id] = agent

    # TODO(ev) this can probably be moved into the superclass
    def reset_map(self):
        self.map = np.full((len(self.base_map), len(self.base_map[0])), ' ')
        self.firing_points = []

        self.build_walls()
        self.update_map_apples(self.apple_points)
        self.setup_agents()

    def update_map(self, agent_actions):
        """Converts agent action tuples into a new map and new agent positions

        Parameters
        ----------
        agent_actions: dict
            dict with agent_id as key and action as value
        """

        self.clean_firing_points()

        for agent_id, action in agent_actions.items():
            agent = self.agents[agent_id]
            selected_action = ACTIONS[action]
            if 'MOVE' in action or 'STAY' in action:
                # rotate the selected action appropriately
                rot_action = self.rotate_action(selected_action, agent.get_orientation())
                new_pos = agent.get_pos() + rot_action
                self.reserved_slots.append((*new_pos, 'P', agent_id))
            elif 'TURN' in action:
                new_rot = self.update_rotation(action, agent.get_orientation())
                agent.update_map_agent_rot(new_rot)
            else:
                agent.fire_beam()
                self.reserved_slots += self.update_map_fire(agent.get_pos().tolist(),
                                                            agent.get_orientation())

    def execute_reservations(self):

        curr_agent_pos = [agent.get_pos().tolist() for agent in self.agents.values()]
        agent_by_pos = {tuple(agent.get_pos()): agent.agent_id for agent in self.agents.values()}

        # agent moves keyed by ids
        agent_moves = {}

        # lists of moves and their corresponding agents
        move_slots = []
        agent_to_slot = []

        apple_pos = []
        firing_pos = []
        for slot in self.reserved_slots:
            row, col = slot[0], slot[1]
            if slot[2] == 'P':
                agent_id = slot[3]
                agent_moves[agent_id] = [row, col]
                move_slots.append([row, col])
                agent_to_slot.append(agent_id)
            elif slot[2] == 'A':
                apple_pos.append([row, col])
            else:
                firing_pos.append([row, col])

        # First, resolve conflicts between two agents that want the same spot
        if len(agent_to_slot) > 0:

            # a random agent will win the slot
            shuffle_list = list(zip(agent_to_slot, move_slots))
            np.random.shuffle(shuffle_list)
            agent_to_slot, move_slots = zip(*shuffle_list)
            unique_move, indices, return_count = np.unique(move_slots, return_index=True,
                                                           return_counts=True, axis=0)
            search_list = np.array(move_slots)
            # if there are any conflicts over a space
            if np.any(return_count > 1):
                for move, index, count in zip(unique_move, indices, return_count):
                    if count > 1:
                        self.agents[agent_to_slot[index]].update_map_agent_pos(move)
                        # remove all the other moves that would have conflicted
                        remove_indices = np.where((search_list == move).all(axis=1))[0]
                        all_agents_id = [agent_to_slot[i] for i in remove_indices]
                        # all other agents now stay in place
                        for agent_id in all_agents_id:
                            agent_moves[agent_id] = self.agents[agent_id].get_pos().tolist()

            for agent_id, move in agent_moves.items():
                if move in curr_agent_pos:
                    # find the agent that is currently at that spot, check where they will be next
                    # if they're going to move away, go ahead and move into their spot
                    conflicting_agent_id = agent_by_pos[tuple(move)]
                    # a STAY command has been issued or the other agent hasn't been issued a command,
                    # don't do anything
                    if agent_id == conflicting_agent_id or \
                            conflicting_agent_id not in agent_moves.keys():
                        continue
                    elif agent_moves[conflicting_agent_id] != move:
                        self.agents[agent_id].update_map_agent_pos(move)
                else:
                    self.agents[agent_id].update_map_agent_pos(move)

        # TODO(ev) move this into a custom execute method, the above is pretty general
        # Next fire the beams
        for pos in firing_pos:
            row, col = pos
            self.map[row, col] = 'F'
            self.firing_points.append([row, col])

        # update the apples
        self.update_map_apples(apple_pos)
        self.reserved_slots = []

    def custom_map_update(self):
        "See parent class"
        # spawn the apples
        new_apples = self.spawn_apples()
        if len(new_apples) > 0:
            self.reserved_slots += new_apples

    def clean_firing_points(self):
        agent_pos = []
        for agent in self.agents.values():
            agent_pos.append(agent.get_pos().tolist())
        for i in range(len(self.firing_points)):
            row, col = self.firing_points[i]
            if self.firing_points[i] in self.hidden_apples:
                self.map[row, col] = 'A'
            elif [row, col] in agent_pos:
                # put the agent back if they were temporarily obscured by the firing beam
                self.map[row, col] = 'P'
            else:
                self.map[row, col] = ' '
        self.hidden_apples = []
        self.firing_points = []

    def spawn_apples(self):
        # iterate over the spawn points in self.ascii_map and compare it with
        # current points in self.map

        new_apple_points = []
        for i in range(len(self.apple_points)):
            row, col = self.apple_points[i]
            window = self.return_view(self.apple_points[i], APPLE_RADIUS, APPLE_RADIUS)
            num_apples = self.count_apples(window)
            spawn_prob = SPAWN_PROB[min(num_apples, 3)]
            rand_num = np.random.rand(1)[0]
            if rand_num < spawn_prob:
                new_apple_points.append((row, col, 'A'))
        return new_apple_points

    def count_apples(self, window):
        # compute how many apples are in window
        unique, counts = np.unique(window, return_counts=True)
        counts_dict = dict(zip(unique, counts))
        num_apples = counts_dict.get('A', 0)
        return num_apples

    def build_walls(self):
        for i in range(len(self.wall_points)):
            row, col = self.wall_points[i]
            self.map[row, col] = '@'

    # FIXME(ev) this is probably shared by every env
    def spawn_point(self):
        """Returns a randomly selected spawn point"""
        not_occupied = False
        rand_int = 0
        # select a spawn point
        # TODO(ev) though it won't ever happen, this can generate an infinite loop and is slow
        # replace this with an operation over a set
        while not not_occupied:
            num_ints = len(self.spawn_points)
            rand_int = np.random.randint(num_ints)
            spawn_point = self.spawn_points[rand_int]
            # FIXME(ev) this will break when we implement rotation colors
            if self.map[spawn_point[0], spawn_point[1]] != 'P':
                not_occupied = True
        return np.array(self.spawn_points[rand_int])

    def spawn_rotation(self):
        """Return a randomly selected initial rotation for an agent"""
        rand_int = np.random.randint(len(ORIENTATIONS.keys()))
        return list(ORIENTATIONS.keys())[rand_int]

    def update_map_fire(self, firing_pos, firing_orientation):
        num_fire_cells = 5
        start_pos = np.asarray(firing_pos)
        firing_direction = ORIENTATIONS[firing_orientation]
        firing_points = []
        for i in range(num_fire_cells):
            next_cell = start_pos + firing_direction
            if self.test_if_in_bounds(next_cell) and self.map[next_cell[0], next_cell[1]] != '@':
                if self.map[next_cell[0], next_cell[1]] == 'A':
                    self.hidden_apples.append([next_cell[0], next_cell[1]])
                self.map[next_cell[0], next_cell[1]] = 'F'
                firing_points.append((next_cell[0], next_cell[1], 'F'))
                start_pos += firing_direction
            else:
                break
        return firing_points

    def update_map_apples(self, new_apple_points):
        for i in range(len(new_apple_points)):
            row, col = new_apple_points[i]
            if self.map[row, col] != 'P' and self.map[row, col] != 'F':
                # TODO(ev) what if a firing beam is here at this time?
                self.map[row, col] = 'A'

    # TODO(ev) this can be a general property of map_env or a util
    def rotate_action(self, action_vec, orientation):
        # WARNING: Note, we adopt the physics convention that \theta=0 is in the +y direction
        if orientation == 'UP':
            return action_vec
        elif orientation == 'LEFT':
            return self.rotate_left(action_vec)
        elif orientation == 'RIGHT':
            return self.rotate_right(action_vec)
        else:
            return self.rotate_left(self.rotate_left(action_vec))

    def rotate_left(self, action_vec):
        return np.dot(ACTIONS['TURN_COUNTERCLOCKWISE'], action_vec)

    def rotate_right(self, action_vec):
        return np.dot(ACTIONS['TURN_CLOCKWISE'], action_vec)

    # TODO(ev) this should be an agent property
    def update_rotation(self, action, curr_orientation):
        if action == 'TURN_COUNTERCLOCKWISE':
            if curr_orientation == 'LEFT':
                return 'DOWN'
            elif curr_orientation == 'DOWN':
                return 'RIGHT'
            elif curr_orientation == 'RIGHT':
                return 'UP'
            else:
                return 'LEFT'
        else:
            if curr_orientation == 'LEFT':
                return 'UP'
            elif curr_orientation == 'UP':
                return 'RIGHT'
            elif curr_orientation == 'RIGHT':
                return 'DOWN'
            else:
                return 'LEFT'

    # TODO(ev) this definitely should go into utils or the general agent class
    def test_if_in_bounds(self, pos):
        """Checks if a selected cell is outside the range of the map"""
        if pos[0] < 0 or pos[0] >= self.map.shape[0]:
            return False
        elif pos[1] < 0 or pos[1] >= self.map.shape[1]:
            return False
        else:
            return True
