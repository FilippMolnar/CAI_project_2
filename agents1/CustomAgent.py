from agents1.OfficialAgent import *


class OngoingTrustCheck(enum.Enum):
    NONE = 1,
    FOUND_RESCUE_MILD = 2, # Waiting for human response
    WAITING_RESCUE_MILD = 3, # Waiting for human arrival
    CARRYING_RESCUE_MILD = 4, # Waiting if victim successfully carried to goal
    FOUND_RESCUE_CRITICAL = 5, # Waiting for human response
    WAITING_RESCUE_CRITICAL = 6, # Waiting for human arrival
    CARRYING_RESCUE_CRITICAL = 7, # Waiting if victim successfully carried to goal
    FOUND_SMALL_ROCK = 8, # Waiting for human response
    WAITING_SMALL_ROCK = 9, # Waiting for human arrival
    FOUND_BIG_ROCK = 10, # Waiting for human response
    WAITING_BIG_ROCK = 11, # Waiting for human arrival
    FOUND_TREE = 12, # Waiting for human response
    WAITING_TREE = 13, # Waiting for human arrival
    COMING_TO_RESCUE_MILD = 14, # Waiting until agent arrives to see if victim exists
    COMING_TO_RESCUE_CRITICAL = 15, # Waiting until agent arrives to see if victim exists
    COMING_TO_OBSTACLE = 16
    # Messages don't distinguish between obstacle types
    # COMING_TO_TREE = 13, # Waiting until agent arrives to see if tree exists
    # COMING_TO_SMALL_ROCK = 14, #  Waiting until agent arrives to see if small rock exists
    # COMING_TO_BIG_ROCK = 15 #  Waiting until agent arrives to see if big rock exists

trust_answer_timeout_lower_bound = 15
trust_answer_timeout_upper_bound = 30
trust_arrive_timeout_lower_bound = 30
trust_arrive_timeout_upper_bound = 60

tree_competence_threshold = -0.25
small_rock_competence_threshold = -0.5
big_rock_competence_threshold = -0.75

mild_victim_competence_threshold = -0.5
critical_victim_competence_threshold = -0.9


class CustomAgent(BaselineAgent):

    def __init__(self, slowdown, condition, name, folder):
        super().__init__(slowdown, condition, name, folder)
        self._trust_beliefs = {} # Current trust values
        self._trust_processed_messages = 0 # Number of processed messages the last time trust was updated
        self._trust_ongoing_check = OngoingTrustCheck.NONE # Past signalling that needs to be cross-checked with world information to update trust
        self._trust_willingness_total = 0 # Total wilingness score assigned to human
        self._trust_competence_total = 0 # Total competence score assigned to human
        self._trust_wilingness_interactions_count = 3 # Dictionary of #interactions with human influencing wilingness
        self._trust_competence_interactions_count = 3 # Dictionary of #interactions with human influencing competence
        self._trust_all_zones_marked_visited = False # When the robot has to search zones again even though human said everything is searched, start counting wrongly marked zones
        self._trust_zones_wrongly_marked_as_searched = []
        self._curr_tick = 0
        self._trust_beliefs['willingness'] = 0
        self._trust_beliefs['competence'] = 0
        """
        Inherited fields (reminder for development)

        self._answered = False
        self._carrying = False
        self._waiting = False
        self._carrying_together = False
        self._remove = False
        self._current_door = None
        self._phase
        self._found_victim_logs = {}
        self._human_loc  - Important! (Likely) Last location human self-reported
        
        """

    def interpolWillingness(self, l, u):
        delta = u - l
        d = (self._trust_beliefs['willingness'] + 1) / 2
        return l + d*delta

    def _updateWillingness(self, delta: int):
        self._trust_willingness_total += delta
        self._trust_wilingness_interactions_count += abs(delta) # To properly calculate weighted average

        # Update willingness using the new weighted average
        self._trust_beliefs['willingness'] = 0 if self._trust_wilingness_interactions_count == 0 else (self._trust_willingness_total / self._trust_wilingness_interactions_count)
        # Clip values between -1 and 1
        self._trust_beliefs['willingness'] = np.clip(self._trust_beliefs['willingness'], -1, 1)
        print("Updated willingness (Change: " + str(delta) + "). New value: " + str(self._trust_beliefs['willingness']))
        self.writeCurrCsv(self._human_name, self._trust_beliefs, self._folder)

    def _updateCompetence(self, delta: int):
        self._trust_competence_total += delta
        self._trust_competence_interactions_count += abs(delta) # To properly calculate weighted average

        # Update competence using the new weighted average
        self._trust_beliefs['competence'] = 0 if self._trust_competence_interactions_count == 0 else (self._trust_competence_total / self._trust_competence_interactions_count)
        # Clip values between -1 and 1
        self._trust_beliefs['competence'] = np.clip(self._trust_beliefs['competence'], -1, 1)
        print("Updated competence (Change: " + str(delta) + "). New value: " + str(self._trust_beliefs['competence']))
        self.writeCurrCsv(self._human_name, self._trust_beliefs, self._folder)

    def writeCurrCsv(self, name, trust_beliefs, folder):
        # Save current trust belief values so we can later use and retrieve them to add to a csv file with all the logged trust belief values
        print("human_name:", name)
        print("competence: ", trust_beliefs['competence'])
        print("willingness: ", trust_beliefs['willingness'])

        with open(folder + '/beliefs/currentTrustBelief.csv', mode='w') as csv_file:
            csv_writer = csv.writer(csv_file, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow(['name', 'competence', 'willingness'])
            csv_writer.writerow([name, trust_beliefs['competence'], trust_beliefs['willingness']])

        return trust_beliefs
    
    def _trustBelief(self, members, trustBeliefs, folder, receivedMessages):
        # Process new messages
        if len(receivedMessages) > self._trust_processed_messages: # New messages received
            for msg in receivedMessages[self._trust_processed_messages:]:
                # Revert 
                if msg.startswith("Search:"):
                    area = msg.split()[-1]
                elif msg.startswith("Found:"):
                    # Identify which victim and area it concerns
                    if len(msg.split()) == 6:
                        foundVic = msg.split()[1:4]
                    else:
                        foundVic = msg.split()[1:5]
                    isCritical = foundVic[0] == "critically"
                    loc = msg.split()[-1]
                elif msg.startswith('Collect:'):
                    # Identify which victim and area it concerns
                    if len(msg.split()) == 6:
                        collectVic = msg.split()[1:4]
                    else:
                        collectVic = msg.split()[1:5]
                    isCritical = collectVic[0] == "critically"
                    loc = msg.split()[-1]
                elif msg.startswith('Remove:'):
                    # Identify at which location the human needs help
                    area = msg.split()[-1]
                    # HUMAN ASKING FOR HELP - REVERT TRUST IMPROVEMENTS FROM ONGOING AGREEMENTS
                    if self._trust_ongoing_check != OngoingTrustCheck.NONE:
                        if self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_SMALL_ROCK:
                            print("[Small rock] Cancelled cooperation")
                            self._updateCompetence(-1)
                        if self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_BIG_ROCK:
                            print("[Big rock] Cancelled cooperation")
                            self._updateCompetence(-1)
                        if self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_RESCUE_MILD:
                            print("[Mild victim] Cancelled cooperation")
                            self._updateCompetence(-2)
                        if self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_RESCUE_CRITICAL:
                            print("[Critical victim] Cancelled cooperation")
                            self._updateCompetence(-4)

            self._trust_processed_messages = len(receivedMessages)

        return trustBeliefs
    

    def decide_on_actions(self, state):
        from worlds1.WorldBuilder import tick_duration
        self._curr_tick = state['World']['nr_ticks']

        # Identify team members
        agent_name = state[self.agent_id]['obj_id']
        for member in state['World']['team_members']:
            if member != agent_name and member not in self._team_members:
                self._team_members.append(member)
        # Create a list of received messages from the human team member
        for mssg in self.received_messages:
            for member in self._team_members:
                if mssg.from_id == member and mssg.content not in self._received_messages:
                    self._received_messages.append(mssg.content)
        # Process messages from team members
        self._process_messages(state, self._team_members, self._condition)
        # Initialize and update trust beliefs for team members
        trustBeliefs = self._loadBelief(self._team_members, self._folder)
        self._trustBelief(self._team_members, trustBeliefs, self._folder, self._received_messages)

        # Check whether human is close in distance
        if state[{'is_human_agent': True}]:
            self._distance_human = 'close'
        if not state[{'is_human_agent': True}]:
            # Define distance between human and agent based on last known area locations
            if self._agent_loc in [1, 2, 3, 4, 5, 6, 7] and self._human_loc in [8, 9, 10, 11, 12, 13, 14]:
                self._distance_human = 'far'
            if self._agent_loc in [1, 2, 3, 4, 5, 6, 7] and self._human_loc in [1, 2, 3, 4, 5, 6, 7]:
                self._distance_human = 'close'
            if self._agent_loc in [8, 9, 10, 11, 12, 13, 14] and self._human_loc in [1, 2, 3, 4, 5, 6, 7]:
                self._distance_human = 'far'
            if self._agent_loc in [8, 9, 10, 11, 12, 13, 14] and self._human_loc in [8, 9, 10, 11, 12, 13, 14]:
                self._distance_human = 'close'

        # Define distance to drop zone based on last known area location
        if self._agent_loc in [1, 2, 5, 6, 8, 9, 11, 12]:
            self._distance_drop = 'far'
        if self._agent_loc in [3, 4, 7, 10, 13, 14]:
            self._distance_drop = 'close'

        # Check whether victims are currently being carried together by human and agent 
        for info in state.values():
            if 'is_human_agent' in info and self._human_name in info['name'] and len(
                    info['is_carrying']) > 0 and 'critical' in info['is_carrying'][0]['obj_id'] or \
                    'is_human_agent' in info and self._human_name in info['name'] and len(
                info['is_carrying']) > 0 and 'mild' in info['is_carrying'][0][
                'obj_id'] and self._rescue == 'together' and not self._moving:
                # If victim is being carried, add to collected victims memory
                if info['is_carrying'][0]['img_name'][8:-4] not in self._collected_victims:
                    self._collected_victims.append(info['is_carrying'][0]['img_name'][8:-4])
                self._carrying_together = True
            if 'is_human_agent' in info and self._human_name in info['name'] and len(info['is_carrying']) == 0:
                self._carrying_together = False
        # If carrying a victim together, let agent be idle (because joint actions are essentially carried out by the human)
        if self._carrying_together == True:
            return None, {}

        # Send the hidden score message for displaying and logging the score during the task, DO NOT REMOVE THIS
        self._send_message('Our score is ' + str(state['rescuebot']['score']) + '.', 'RescueBot')

        # Ongoing loop until the task is terminated, using different phases for defining the agent's behavior
        while True:
            if Phase.INTRO == self._phase:
                # Send introduction message
                self._send_message('Hello! My name is RescueBot. Together we will collaborate and try to search and rescue the 8 victims on our right as quickly as possible. \
                Each critical victim (critically injured girl/critically injured elderly woman/critically injured man/critically injured dog) adds 6 points to our score, \
                each mild victim (mildly injured boy/mildly injured elderly man/mildly injured woman/mildly injured cat) 3 points. \
                If you are ready to begin our mission, you can simply start moving.', 'RescueBot')
                # Wait untill the human starts moving before going to the next phase, otherwise remain idle
                if not state[{'is_human_agent': True}]:
                    self._phase = Phase.FIND_NEXT_GOAL
                else:
                    return None, {}

            if Phase.FIND_NEXT_GOAL == self._phase:
                # Definition of some relevant variables
                self._answered = False
                self._goal_vic = None
                self._goal_loc = None
                self._rescue = None
                self._moving = True
                remaining_zones = []
                remaining_vics = []
                remaining = {}
                # Identification of the location of the drop zones
                zones = self._get_drop_zones(state)
                # Identification of which victims still need to be rescued and on which location they should be dropped
                for info in zones:
                    if str(info['img_name'])[8:-4] not in self._collected_victims:
                        remaining_zones.append(info)
                        remaining_vics.append(str(info['img_name'])[8:-4])
                        remaining[str(info['img_name'])[8:-4]] = info['location']
                if remaining_zones:
                    self._remainingZones = remaining_zones
                    self._remaining = remaining
                # Remain idle if there are no victims left to rescue
                if not remaining_zones:
                    return None, {}

                # Check which victims can be rescued next because human or agent already found them
                for vic in remaining_vics:
                    # Define a previously found victim as target victim because all areas have been searched
                    if vic in self._found_victims and vic in self._todo and len(self._searched_rooms) == 0:
                        self._goal_vic = vic
                        self._goal_loc = remaining[vic]
                        # Move to target victim
                        self._rescue = 'together'
                        self._send_message('Moving to ' + self._found_victim_logs[vic][
                            'room'] + ' to pick up ' + self._goal_vic + '. Please come there as well to help me carry ' + self._goal_vic + ' to the drop zone.',
                                          'RescueBot')
                        
                        # TRUST
                        if self._goal_vic.split()[0] == "mildly":
                            self._trust_ongoing_check = (self._curr_tick, self._found_victim_logs[vic]['room'], OngoingTrustCheck.WAITING_RESCUE_MILD)
                        else:
                            self._trust_ongoing_check = (self._curr_tick, self._found_victim_logs[vic]['room'], OngoingTrustCheck.WAITING_RESCUE_CRITICAL)

                        # Plan path to victim because the exact location is known (i.e., the agent found this victim)
                        if 'location' in self._found_victim_logs[vic].keys():
                            self._phase = Phase.PLAN_PATH_TO_VICTIM
                            return Idle.__name__, {'duration_in_ticks': 25}
                        # Plan path to area because the exact victim location is not known, only the area (i.e., human found this  victim)
                        if 'location' not in self._found_victim_logs[vic].keys():
                            self._phase = Phase.PLAN_PATH_TO_ROOM
                            return Idle.__name__, {'duration_in_ticks': 25}
                    # Define a previously found victim as target victim
                    if vic in self._found_victims and vic not in self._todo:
                        self._goal_vic = vic
                        self._goal_loc = remaining[vic]
                        # Rescue together when victim is critical or when the human is weak and the victim is mildly injured
                        if 'critical' in vic or 'mild' in vic and self._condition == 'weak':
                            self._rescue = 'together'
                        # Rescue alone if the victim is mildly injured and the human not weak
                        if 'mild' in vic and self._condition != 'weak':
                            self._rescue = 'alone'
                        # Plan path to victim because the exact location is known (i.e., the agent found this victim)
                        if 'location' in self._found_victim_logs[vic].keys():
                            self._phase = Phase.PLAN_PATH_TO_VICTIM
                            return Idle.__name__, {'duration_in_ticks': 25}
                        # Plan path to area because the exact victim location is not known, only the area (i.e., human found this  victim)
                        if 'location' not in self._found_victim_logs[vic].keys():
                            self._phase = Phase.PLAN_PATH_TO_ROOM
                            return Idle.__name__, {'duration_in_ticks': 25}
                    # If there are no target victims found, visit an unsearched area to search for victims
                    if vic not in self._found_victims or vic in self._found_victims and vic in self._todo and len(
                            self._searched_rooms) > 0:
                        self._phase = Phase.PICK_UNSEARCHED_ROOM

            if Phase.PICK_UNSEARCHED_ROOM == self._phase:
                agent_location = state[self.agent_id]['location']
                # Identify which areas are not explored yet
                unsearched_rooms = [room['room_name'] for room in state.values()
                                   if 'class_inheritance' in room
                                   and 'Door' in room['class_inheritance']
                                   and room['room_name'] not in self._searched_rooms
                                   and room['room_name'] not in self._to_search]
                # If all areas have been searched but the task is not finished, start searching areas again
                if self._remainingZones and len(unsearched_rooms) == 0:
                    # TRUST - Start counting wrongly marked visited zones still with victims
                    self._trust_all_zones_marked_visited = True

                    self._to_search = []
                    self._searched_rooms = []
                    self._send_messages = []
                    self.received_messages = []
                    self.received_messages_content = []
                    self._send_message('Going to re-search all areas.', 'RescueBot')
                    self._phase = Phase.FIND_NEXT_GOAL
                # If there are still areas to search, define which one to search next
                else:
                    # Identify the closest door when the agent did not search any areas yet
                    if self._current_door == None:
                        # Find all area entrance locations
                        self._door = state.get_room_doors(self._getClosestRoom(state, unsearched_rooms, agent_location))[
                            0]
                        self._doormat = \
                            state.get_room(self._getClosestRoom(state, unsearched_rooms, agent_location))[-1]['doormat']
                        # Workaround for one area because of some bug
                        if self._door['room_name'] == 'area 1':
                            self._doormat = (3, 5)
                        # Plan path to area
                        self._phase = Phase.PLAN_PATH_TO_ROOM
                    # Identify the closest door when the agent just searched another area
                    if self._current_door != None:
                        self._door = \
                            state.get_room_doors(self._getClosestRoom(state, unsearched_rooms, self._current_door))[0]
                        self._doormat = \
                            state.get_room(self._getClosestRoom(state, unsearched_rooms, self._current_door))[-1][
                                'doormat']
                        if self._door['room_name'] == 'area 1':
                            self._doormat = (3, 5)
                        self._phase = Phase.PLAN_PATH_TO_ROOM

            if Phase.PLAN_PATH_TO_ROOM == self._phase:
                # Reset the navigator for a new path planning
                self._navigator.reset_full()

                # Check if there is a goal victim, and it has been found, but its location is not known
                if self._goal_vic \
                        and self._goal_vic in self._found_victims \
                        and 'location' not in self._found_victim_logs[self._goal_vic].keys():
                    # Retrieve the victim's room location and related information
                    victim_location = self._found_victim_logs[self._goal_vic]['room']
                    self._door = state.get_room_doors(victim_location)[0]
                    self._doormat = state.get_room(victim_location)[-1]['doormat']

                    # Handle special case for 'area 1'
                    if self._door['room_name'] == 'area 1':
                        self._doormat = (3, 5)

                    # Set the door location based on the doormat
                    doorLoc = self._doormat

                # If the goal victim's location is known, plan the route to the identified area
                else:
                    if self._door['room_name'] == 'area 1':
                        self._doormat = (3, 5)
                    doorLoc = self._doormat

                # Add the door location as a waypoint for navigation
                self._navigator.add_waypoints([doorLoc])
                # Follow the route to the next area to search
                self._phase = Phase.FOLLOW_PATH_TO_ROOM

            if Phase.FOLLOW_PATH_TO_ROOM == self._phase:
                # Check if the previously identified target victim was rescued by the human
                if self._goal_vic and self._goal_vic in self._collected_victims:
                    # Reset current door and switch to finding the next goal
                    self._current_door = None
                    self._phase = Phase.FIND_NEXT_GOAL

                # Check if the human found the previously identified target victim in a different room
                if self._goal_vic \
                        and self._goal_vic in self._found_victims \
                        and self._door['room_name'] != self._found_victim_logs[self._goal_vic]['room']:
                    self._current_door = None
                    self._phase = Phase.FIND_NEXT_GOAL

                # Check if the human already searched the previously identified area without finding the target victim
                if self._door['room_name'] in self._searched_rooms and self._goal_vic not in self._found_victims:
                    self._current_door = None
                    self._phase = Phase.FIND_NEXT_GOAL

                # Move to the next area to search
                else:
                    # Update the state tracker with the current state
                    self._state_tracker.update(state)

                    # Explain why the agent is moving to the specific area, either:
                    # [-] it contains the current target victim
                    # [-] it is the closest un-searched area
                    if self._goal_vic in self._found_victims \
                            and str(self._door['room_name']) == self._found_victim_logs[self._goal_vic]['room'] \
                            and not self._remove:
                        if self._condition == 'weak':
                            self._send_message('Moving to ' + str(
                                self._door['room_name']) + ' to pick up ' + self._goal_vic + ' together with you.',
                                              'RescueBot')
                        else:
                            self._send_message(
                                'Moving to ' + str(self._door['room_name']) + ' to pick up ' + self._goal_vic + '.',
                                'RescueBot')

                    if self._goal_vic not in self._found_victims and not self._remove or not self._goal_vic and not self._remove:
                        self._send_message(
                            'Moving to ' + str(self._door['room_name']) + ' because it is the closest unsearched area.',
                            'RescueBot')

                    # Set the current door based on the current location
                    self._current_door = self._door['location']

                    # Retrieve move actions to execute
                    action = self._navigator.get_move_action(self._state_tracker)
                    # Check for obstacles blocking the path to the area and handle them if needed
                    if action is not None:
                        # Remove obstacles blocking the path to the area 
                        for info in state.values():
                            if 'class_inheritance' in info and 'ObstacleObject' in info[
                                'class_inheritance'] and 'stone' in info['obj_id'] and info['location'] not in [(9, 4),
                                                                                                                (9, 7),
                                                                                                                (9, 19),
                                                                                                                (21,
                                                                                                                 19)]:
                                self._send_message('Reaching ' + str(self._door['room_name'])
                                                   + ' will take a bit longer because I found stones blocking my path.',
                                                   'RescueBot')
                                return RemoveObject.__name__, {'object_id': info['obj_id']}
                        return action, {}
                    # Identify and remove obstacles if they are blocking the entrance of the area
                    self._phase = Phase.REMOVE_OBSTACLE_IF_NEEDED

            if Phase.REMOVE_OBSTACLE_IF_NEEDED == self._phase:
                objects = []
                agent_location = state[self.agent_id]['location']
                # Identify which obstacle is blocking the entrance
                for info in state.values():
                    # BIG ROCK
                    if 'class_inheritance' in info and 'ObstacleObject' in info['class_inheritance'] and 'rock' in info[
                        'obj_id']:
                        objects.append(info)

                        # DECISION: Continue, if competence too low
                        if self._trust_beliefs['competence'] < big_rock_competence_threshold:
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL

                            # TRUST - Remove ongoing check
                            print("[Big rock] Forced Continue")
                            self._updateCompetence(0)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                        # Communicate which obstacle is blocking the entrance
                        if self._answered == False and not self._remove and not self._waiting:
                            self._send_message('Found rock blocking ' + str(self._door['room_name']) + '. Please decide whether to "Remove" or "Continue" searching. \n \n \
                                Important features to consider are: \n safe - victims rescued: ' + str(
                                self._collected_victims) + ' \n explore - areas searched: area ' + str(
                                self._searched_rooms).replace('area ', '') + ' \
                                \n clock - removal time: 5 seconds \n afstand - distance between us: ' + self._distance_human,
                                              'RescueBot')
                            self._waiting = True

                            # TRUST - Set ongoing status
                            self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.FOUND_BIG_ROCK)
                        
                        # HUMAN IGNORES FOR trust_answer_timeout
                        if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._answered == False and not self._remove and self._waiting and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_answer_timeout_lower_bound, trust_answer_timeout_upper_bound):
                            # TRUST - Human ignored question. Lower willingness.
                            print("[Big rock] Ignore question")
                            self._updateWillingness(-2)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            # IGNORED - Continue
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL
                            return None, {}

                        if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_BIG_ROCK and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_arrive_timeout_lower_bound, trust_arrive_timeout_upper_bound):
                            # TRUST - Human did not arrive
                            print("[Big rock] Did not arrive or act in time to remove together")
                            self._updateCompetence(-1)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            # IGNORED - Continue
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL
                            return None, {}


                        # Determine the next area to explore if the human tells the agent not to remove the obstacle
                        if self.received_messages_content and self.received_messages_content[
                            -1] == 'Continue' and not self._remove:
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL

                            # TRUST - Remove ongoing check
                            print("[Big rock] Continue")
                            self._updateWillingness(-0.5)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                        # Wait for the human to help removing the obstacle and remove the obstacle together
                        if self.received_messages_content and self.received_messages_content[
                            -1] == 'Remove' or self._remove:
                            # TRUST - Update ongoing check
                            if self._trust_ongoing_check == OngoingTrustCheck.NONE or self._trust_ongoing_check[2] != OngoingTrustCheck.WAITING_BIG_ROCK:
                                print("[Big rock] Agreed to remove together")
                                self._updateWillingness(1)
                                self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.WAITING_BIG_ROCK)

                            if not self._remove:
                                self._answered = True
                            # Tell the human to come over and be idle untill human arrives
                            if not state[{'is_human_agent': True}]:
                                self._send_message('Please come to ' + str(self._door['room_name']) + ' to remove rock.',
                                                  'RescueBot')
                                return None, {}
                            
                            # Tell the human to remove the obstacle when he/she arrives
                            if state[{'is_human_agent': True}]:
                                self._send_message('Lets remove rock blocking ' + str(self._door['room_name']) + '!',
                                                  'RescueBot')
                                return None, {}
                        # Remain idle until the human communicates what to do with the identified obstacle 
                        else:
                            return None, {}

                    
                    # TREE
                    if 'class_inheritance' in info and 'ObstacleObject' in info['class_inheritance'] and 'tree' in info[
                        'obj_id']:
                        objects.append(info)

                        # DECISION: Remove automatically, if competence too low
                        if self._trust_beliefs['competence'] < tree_competence_threshold:
                            # Update ongoing check
                            print("[Tree] Forced removal")
                            self._updateCompetence(0)
                            self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.WAITING_TREE)

                            self._answered = True
                            self._waiting = False
                            self._send_message('Removing tree blocking ' + str(self._door['room_name']) + '.',
                                            'RescueBot')
                            self._phase = Phase.ENTER_ROOM
                            self._remove = False
                            return RemoveObject.__name__, {'object_id': info['obj_id']}

                        # Communicate which obstacle is blocking the entrance
                        if self._answered == False and not self._remove and not self._waiting:
                            self._send_message('Found tree blocking  ' + str(self._door['room_name']) + '. Please decide whether to "Remove" or "Continue" searching. \n \n \
                                Important features to consider are: \n safe - victims rescued: ' + str(
                                self._collected_victims) + '\n explore - areas searched: area ' + str(
                                self._searched_rooms).replace('area ', '') + ' \
                                \n clock - removal time: 10 seconds', 'RescueBot')
                            self._waiting = True

                            # TRUST - Set ongoing status
                            self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.FOUND_TREE)
                        
                        # HUMAN IGNORES FOR trust_answer_timeout
                        if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._answered == False and not self._remove and self._waiting and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_answer_timeout_lower_bound, trust_answer_timeout_upper_bound):
                            # TRUST - Human ignored question. Lower willingness.
                            print("[Tree] Ignored question")
                            self._updateWillingness(-2)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            # IGNORED - Continue
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL
                        
                        # Determine the next area to explore if the human tells the agent not to remove the obstacle
                        if self.received_messages_content and self.received_messages_content[
                            -1] == 'Continue' and not self._remove:
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL

                            # TRUST - Remove ongoing check
                            print("[Tree] Continue")
                            self._updateWillingness(-0.5)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                        # Remove the obstacle if the human tells the agent to do so
                        if self.received_messages_content and self.received_messages_content[
                            -1] == 'Remove' or self._remove:

                            # Update ongoing check
                            print("[Tree] Confirmed removal")
                            self._updateWillingness(0)
                            self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.WAITING_TREE)

                            if not self._remove:
                                self._answered = True
                                self._waiting = False
                                self._send_message('Removing tree blocking ' + str(self._door['room_name']) + '.',
                                                  'RescueBot')
                            if self._remove:
                                self._send_message('Removing tree blocking ' + str(
                                    self._door['room_name']) + ' because you asked me to.', 'RescueBot')
                            self._phase = Phase.ENTER_ROOM
                            self._remove = False
                            return RemoveObject.__name__, {'object_id': info['obj_id']}
                        # Remain idle untill the human communicates what to do with the identified obstacle

                        else:
                            return None, {}

                    # SMALL ROCK
                    if 'class_inheritance' in info and 'ObstacleObject' in info['class_inheritance'] and 'stone' in \
                            info['obj_id']:
                        objects.append(info)

                        # DECISION: Remove automatically, if competence too low
                        if self._trust_beliefs['competence'] < small_rock_competence_threshold:
                            # TRUST - Remove ongoing check
                            print("[Small rock] Forced removal alone")
                            self._updateCompetence(0)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            self._answered = True
                            self._waiting = False
                            self._send_message('Removing stones blocking ' + str(self._door['room_name']) + '.',
                                              'RescueBot')
                            self._phase = Phase.ENTER_ROOM
                            self._remove = False
                            return RemoveObject.__name__, {'object_id': info['obj_id']}

                        # Communicate which obstacle is blocking the entrance
                        if self._answered == False and not self._remove and not self._waiting:
                            self._send_message('Found stones blocking  ' + str(self._door['room_name']) + '. Please decide whether to "Remove together", "Remove alone", or "Continue" searching. \n \n \
                                Important features to consider are: \n safe - victims rescued: ' + str(
                                self._collected_victims) + ' \n explore - areas searched: area ' + str(
                                self._searched_rooms).replace('area', '') + ' \
                                \n clock - removal time together: 3 seconds \n afstand - distance between us: ' + self._distance_human + '\n clock - removal time alone: 20 seconds',
                                              'RescueBot')
                            self._waiting = True

                            # TRUST - Set ongoing status
                            self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.FOUND_SMALL_ROCK)

                        # HUMAN IGNORES FOR trust_answer_timeout
                        if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._answered == False and not self._remove and self._waiting and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_answer_timeout_lower_bound, trust_answer_timeout_upper_bound):
                            # TRUST - Human ignored question. Lower willingness.
                            print("[Small rock] Ignored question")
                            self._updateWillingness(-1)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            # IGNORED - Continue
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL
                            return None, {}

                        # HUMAN DID NOT ARRIVE IN TIME
                        if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_SMALL_ROCK and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_arrive_timeout_lower_bound, trust_arrive_timeout_upper_bound):
                            # TRUST - Human did not arrive
                            print("[Small rock] Did not arrive or act in time")
                            self._updateCompetence(-1)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            # IGNORED - Continue
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL
                            return None, {}

                        # Determine the next area to explore if the human tells the agent not to remove the obstacle          
                        if self.received_messages_content and self.received_messages_content[
                            -1] == 'Continue' and not self._remove:
                            self._answered = True
                            self._waiting = False
                            # Add area to the to do list
                            self._to_search.append(self._door['room_name'])
                            self._phase = Phase.FIND_NEXT_GOAL

                            # TRUST - Remove ongoing check
                            print("[Small rock] Continue")
                            self._updateWillingness(-0.5)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                        # Remove the obstacle alone if the human decides so
                        if self.received_messages_content and self.received_messages_content[
                            -1] == 'Remove alone' and not self._remove:

                            # TRUST - Remove ongoing check
                            print("[Small rock] Remove alone")
                            self._updateWillingness(-1)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            self._answered = True
                            self._waiting = False
                            self._send_message('Removing stones blocking ' + str(self._door['room_name']) + '.',
                                              'RescueBot')
                            self._phase = Phase.ENTER_ROOM
                            self._remove = False
                            return RemoveObject.__name__, {'object_id': info['obj_id']}
                        # Remove the obstacle together if the human decides so
                        if self.received_messages_content and self.received_messages_content[
                            -1] == 'Remove together' or self._remove:

                            # TRUST - Update ongoing check
                            if self._trust_ongoing_check == OngoingTrustCheck.NONE or self._trust_ongoing_check[2] != OngoingTrustCheck.WAITING_SMALL_ROCK:
                                print("[Small rock] Agreed to remove together")
                                self._updateWillingness(1)
                                self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.WAITING_SMALL_ROCK)

                            if not self._remove:
                                self._answered = True
                            # Tell the human to come over and be idle untill human arrives
                            if not state[{'is_human_agent': True}]:
                                self._send_message(
                                    'Please come to ' + str(self._door['room_name']) + ' to remove stones together.',
                                    'RescueBot')
                                return None, {}
                            # Tell the human to remove the obstacle when he/she arrives
                            if state[{'is_human_agent': True}]:
                                self._send_message('Lets remove stones blocking ' + str(self._door['room_name']) + '!',
                                                  'RescueBot')
                                return None, {}
                        # Remain idle until the human communicates what to do with the identified obstacle
                        else:
                            return None, {}

                # If no obstacles are blocking the entrance, enter the area
                if len(objects) == 0:
                    self._answered = False
                    self._remove = False
                    self._waiting = False
                    self._phase = Phase.ENTER_ROOM

                    # TRUST - if object successfully removed together, improve trust
                    if self._trust_ongoing_check != OngoingTrustCheck.NONE:
                        if self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_SMALL_ROCK:
                            print("[Small rock] Removed together successfully")
                            self._updateCompetence(1)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE
                        elif self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_BIG_ROCK:
                            print("[Big rock] Removed together successfully")
                            self._updateCompetence(2)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE
                        elif self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_TREE:
                            print("[Tree] Removed (human did not help so no competence change)")
                            self._updateCompetence(0)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE
                    
            if Phase.ENTER_ROOM == self._phase:
                self._answered = False

                # Check if the target victim has been rescued by the human, and switch to finding the next goal
                if self._goal_vic in self._collected_victims:
                    self._current_door = None
                    self._phase = Phase.FIND_NEXT_GOAL

                # Check if the target victim is found in a different area, and start moving there
                if self._goal_vic in self._found_victims \
                        and self._door['room_name'] != self._found_victim_logs[self._goal_vic]['room']:
                    self._current_door = None
                    self._phase = Phase.FIND_NEXT_GOAL

                # Check if area already searched without finding the target victim, and plan to search another area
                if self._door['room_name'] in self._searched_rooms and self._goal_vic not in self._found_victims:
                    self._current_door = None
                    self._phase = Phase.FIND_NEXT_GOAL

                # Enter the area and plan to search it
                else:
                    self._state_tracker.update(state)

                    action = self._navigator.get_move_action(self._state_tracker)
                    # If there is a valid action, return it; otherwise, plan to search the room
                    if action is not None:
                        return action, {}
                    self._phase = Phase.PLAN_ROOM_SEARCH_PATH

            if Phase.PLAN_ROOM_SEARCH_PATH == self._phase:
                # Extract the numeric location from the room name and set it as the agent's location
                self._agent_loc = int(self._door['room_name'].split()[-1])

                # Store the locations of all area tiles in the current room
                room_tiles = [info['location'] for info in state.values()
                             if 'class_inheritance' in info
                             and 'AreaTile' in info['class_inheritance']
                             and 'room_name' in info
                             and info['room_name'] == self._door['room_name']]
                self._roomtiles = room_tiles

                # Make the plan for searching the area
                self._navigator.reset_full()
                self._navigator.add_waypoints(self._efficientSearch(room_tiles))

                # Initialize variables for storing room victims and switch to following the room search path
                self._room_vics = []
                self._phase = Phase.FOLLOW_ROOM_SEARCH_PATH

            if Phase.FOLLOW_ROOM_SEARCH_PATH == self._phase:
                # Search the area
                self._state_tracker.update(state)
                action = self._navigator.get_move_action(self._state_tracker)
                if action != None:
                    # Identify victims present in the area
                    for info in state.values():
                        if 'class_inheritance' in info and 'CollectableBlock' in info['class_inheritance']:
                            vic = str(info['img_name'][8:-4])
                            # Remember which victim the agent found in this area
                            if vic not in self._room_vics:
                                self._room_vics.append(vic)

                            # Identify the exact location of the victim that was found by the human earlier
                            if vic in self._found_victims and 'location' not in self._found_victim_logs[vic].keys():
                                self._recent_vic = vic
                                # Add the exact victim location to the corresponding dictionary
                                self._found_victim_logs[vic] = {'location': info['location'],
                                                                'room': self._door['room_name'],
                                                                'obj_id': info['obj_id']}
                                if vic == self._goal_vic:
                                    # Communicate which victim was found
                                    self._send_message('Found ' + vic + ' in ' + self._door[
                                        'room_name'] + ' because you told me ' + vic + ' was located here.',
                                                      'RescueBot')
                                    
                                    # TRUST
                                    print("[Inform about victim] Victim was truly where human said it was")
                                    if vic.split()[0] == 'mildly':
                                        self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.WAITING_RESCUE_MILD)
                                    else:
                                        self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.WAITING_RESCUE_CRITICAL)
                                    self._updateCompetence(1)

                                    # Add the area to the list with searched areas
                                    if self._door['room_name'] not in self._searched_rooms:
                                        self._searched_rooms.append(self._door['room_name'])
                                    # Do not continue searching the rest of the area but start planning to rescue the victim
                                    self._phase = Phase.FIND_NEXT_GOAL

                            # Identify injured victim in the area
                            if 'healthy' not in vic and vic not in self._found_victims:
                                self._recent_vic = vic
                                # Add the victim and the location to the corresponding dictionary
                                self._found_victims.append(vic)
                                self._found_victim_logs[vic] = {'location': info['location'],
                                                                'room': self._door['room_name'],
                                                                'obj_id': info['obj_id']}
                                # If searching rooms again because human incorrectly marked as visited, update trust
                                if self._trust_all_zones_marked_visited and not self._door['room_name'] in self._trust_zones_wrongly_marked_as_searched:
                                    print("[Room " + str(self._door['room_name']) + "] Incorrectly marked as 'searched'")
                                    self._trust_zones_wrongly_marked_as_searched.append(self._door['room_name'])
                                    self._updateCompetence(-2)


                                # Communicate which victim the agent found and ask the human whether to rescue the victim now or at a later stage
                                if 'mild' in vic and self._answered == False and not self._waiting:
                                    # DECISION: Rescue mild victim alone, if competence too low
                                    if self._trust_beliefs['competence'] < mild_victim_competence_threshold:
                                        self._send_message('Picking up ' + self._recent_vic + ' in ' + self._door['room_name'] + '.',
                                                        'RescueBot')
                                        # TRUST
                                        print("[Mild victim] Forced rescue alone")
                                        self._updateCompetence(0)

                                        self._rescue = 'alone'
                                        self._answered = True
                                        self._waiting = False
                                        self._goal_vic = self._recent_vic
                                        self._goal_loc = self._remaining[self._goal_vic]
                                        self._recent_vic = None
                                        self._phase = Phase.PLAN_PATH_TO_VICTIM
                                    
                                    else:
                                        self._send_message('Found ' + vic + ' in ' + self._door['room_name'] + '. Please decide whether to "Rescue together", "Rescue alone", or "Continue" searching. \n \n \
                                            Important features to consider are: \n safe - victims rescued: ' + str(
                                            self._collected_victims) + '\n explore - areas searched: area ' + str(
                                            self._searched_rooms).replace('area ', '') + '\n \
                                            clock - extra time when rescuing alone: 15 seconds \n afstand - distance between us: ' + self._distance_human,
                                                        'RescueBot')
                                        self._waiting = True
                                        self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.FOUND_RESCUE_MILD)

                                if 'critical' in vic and self._answered == False and not self._waiting:
                                    # DECISION: Rescue mild victim alone, if competence too low
                                    if self._trust_beliefs['competence'] < critical_victim_competence_threshold:
                                        print("[Critical victim] Forced continue")
                                        self._updateCompetence(0)

                                        self._answered = True
                                        self._waiting = False
                                        self._todo.append(self._recent_vic)
                                        self._recent_vic = None
                                        self._phase = Phase.FIND_NEXT_GOAL

                                    else:
                                        self._send_message('Found ' + vic + ' in ' + self._door['room_name'] + '. Please decide whether to "Rescue" or "Continue" searching. \n\n \
                                            Important features to consider are: \n explore - areas searched: area ' + str(
                                            self._searched_rooms).replace('area',
                                                                        '') + ' \n safe - victims rescued: ' + str(
                                            self._collected_victims) + '\n \
                                            afstand - distance between us: ' + self._distance_human, 'RescueBot')
                                        self._waiting = True
                                        self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.FOUND_RESCUE_CRITICAL)

                                    # Execute move actions to explore the area
                    return action, {}

                # Communicate that the agent did not find the target victim in the area while the human previously communicated the victim was located here
                if self._goal_vic in self._found_victims and self._goal_vic not in self._room_vics and \
                        self._found_victim_logs[self._goal_vic]['room'] == self._door['room_name']:
                    self._send_message(self._goal_vic + ' not present in ' + str(self._door[
                                                                                    'room_name']) + ' because I searched the whole area without finding ' + self._goal_vic + '.',
                                      'RescueBot')
                    
                    print("[Inform about victim] Victim was NOT where human said it was")
                    self._updateCompetence(-2)

                    # Remove the victim location from memory
                    self._found_victim_logs.pop(self._goal_vic, None)
                    self._found_victims.remove(self._goal_vic)
                    self._room_vics = []
                    # Reset received messages (bug fix)
                    self.received_messages = []
                    self.received_messages_content = []
                # Add the area to the list of searched areas
                if self._door['room_name'] not in self._searched_rooms:
                    self._searched_rooms.append(self._door['room_name'])
                # Make a plan to rescue a found critically injured victim if the human decides so
                if self.received_messages_content and self.received_messages_content[
                    -1] == 'Rescue' and 'critical' in self._recent_vic:
                    self._rescue = 'together'
                    self._answered = True
                    self._waiting = False
                    # TRUST
                    self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.WAITING_RESCUE_CRITICAL)
                    print("[Critical victim] Trying to rescue together")
                    self._updateWillingness(2)

                    # Tell the human to come over and help carry the critically injured victim
                    if not state[{'is_human_agent': True}]:
                        self._send_message('Please come to ' + str(self._door['room_name']) + ' to carry ' + str(
                            self._recent_vic) + ' together.', 'RescueBot')
                    # Tell the human to carry the critically injured victim together
                    if state[{'is_human_agent': True}]:
                        self._send_message('Lets carry ' + str(
                            self._recent_vic) + ' together! Please wait until I moved on top of ' + str(
                            self._recent_vic) + '.', 'RescueBot')
                    self._goal_vic = self._recent_vic
                    self._recent_vic = None
                    self._phase = Phase.PLAN_PATH_TO_VICTIM
                # Make a plan to rescue a found mildly injured victim together if the human decides so
                if self.received_messages_content and self.received_messages_content[
                    -1] == 'Rescue together' and 'mild' in self._recent_vic:
                    self._rescue = 'together'
                    self._answered = True
                    self._waiting = False
                    # TRUST
                    self._trust_ongoing_check = (self._curr_tick, self._door['room_name'], OngoingTrustCheck.WAITING_RESCUE_MILD)
                    print("[Mild victim] Trying to rescue together")
                    self._updateWillingness(1)

                    # Tell the human to come over and help carry the mildly injured victim
                    if not state[{'is_human_agent': True}]:
                        self._send_message('Please come to ' + str(self._door['room_name']) + ' to carry ' + str(
                            self._recent_vic) + ' together.', 'RescueBot')
                    # Tell the human to carry the mildly injured victim together
                    if state[{'is_human_agent': True}]:
                        self._send_message('Lets carry ' + str(
                            self._recent_vic) + ' together! Please wait until I moved on top of ' + str(
                            self._recent_vic) + '.', 'RescueBot')
                    self._goal_vic = self._recent_vic
                    self._recent_vic = None
                    self._phase = Phase.PLAN_PATH_TO_VICTIM
                # Make a plan to rescue the mildly injured victim alone if the human decides so, and communicate this to the human
                if self.received_messages_content and self.received_messages_content[
                    -1] == 'Rescue alone' and 'mild' in self._recent_vic:
                    self._send_message('Picking up ' + self._recent_vic + ' in ' + self._door['room_name'] + '.',
                                      'RescueBot')
                    # TRUST
                    print("[Mild victim] Rescue alone")
                    self._updateWillingness(-1)

                    self._rescue = 'alone'
                    self._answered = True
                    self._waiting = False
                    self._goal_vic = self._recent_vic
                    self._goal_loc = self._remaining[self._goal_vic]
                    self._recent_vic = None
                    self._phase = Phase.PLAN_PATH_TO_VICTIM
                # Continue searching other areas if the human decides so
                if self.received_messages_content and self.received_messages_content[-1] == 'Continue':
                    # TRUST
                    if 'mild' in self._recent_vic:
                        print("[Mild victim] Continue")
                        self._updateWillingness(-1)
                    else:
                        print("[Critical victim] Continue")
                        self._updateWillingness(-2)

                    self._answered = True
                    self._waiting = False
                    self._todo.append(self._recent_vic)
                    self._recent_vic = None
                    self._phase = Phase.FIND_NEXT_GOAL
                # Remain idle untill the human communicates to the agent what to do with the found victim
                if self.received_messages_content and self._waiting and self.received_messages_content[
                    -1] != 'Rescue' and self.received_messages_content[-1] != 'Continue':
                    # HUMAN IGNORED QUESTION - MILD
                    if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._trust_ongoing_check[2] == OngoingTrustCheck.FOUND_RESCUE_MILD and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_answer_timeout_lower_bound, trust_answer_timeout_upper_bound):
                        # TRUST - Human did not respond
                        print("[Mild victim] Ignored question")
                        self._updateWillingness(-2)
                        self._trust_ongoing_check = OngoingTrustCheck.NONE

                        # IGNORED - Continue
                        self._answered = True
                        self._waiting = False
                        self._todo.append(self._recent_vic)
                        self._recent_vic = None
                        self._phase = Phase.FIND_NEXT_GOAL

                    # HUMAN IGNORED QUESTION - CRITICAL
                    if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._trust_ongoing_check[2] == OngoingTrustCheck.FOUND_RESCUE_CRITICAL and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_answer_timeout_lower_bound, trust_answer_timeout_upper_bound):
                        # TRUST - Human did not respond
                        print("[Critical victim] Ignored question")
                        self._updateWillingness(-4)
                        self._trust_ongoing_check = OngoingTrustCheck.NONE

                        # IGNORED - Continue
                        self._answered = True
                        self._waiting = False
                        self._todo.append(self._recent_vic)
                        self._recent_vic = None
                        self._phase = Phase.FIND_NEXT_GOAL
                    return None, {}
                # Find the next area to search when the agent is not waiting for an answer from the human or occupied with rescuing a victim
                if not self._waiting and not self._rescue:
                    self._recent_vic = None
                    self._phase = Phase.FIND_NEXT_GOAL
                return Idle.__name__, {'duration_in_ticks': 25}

            if Phase.PLAN_PATH_TO_VICTIM == self._phase:
                # Plan the path to a found victim using its location
                self._navigator.reset_full()
                self._navigator.add_waypoints([self._found_victim_logs[self._goal_vic]['location']])
                # Follow the path to the found victim
                self._phase = Phase.FOLLOW_PATH_TO_VICTIM

            if Phase.FOLLOW_PATH_TO_VICTIM == self._phase:
                # Start searching for other victims if the human already rescued the target victim
                if self._goal_vic and self._goal_vic in self._collected_victims:
                    self._phase = Phase.FIND_NEXT_GOAL

                # Move towards the location of the found victim
                else:
                    self._state_tracker.update(state)

                    action = self._navigator.get_move_action(self._state_tracker)
                    # If there is a valid action, return it; otherwise, switch to taking the victim
                    if action is not None:
                        return action, {}
                    self._phase = Phase.TAKE_VICTIM

            if Phase.TAKE_VICTIM == self._phase:
                # Store all area tiles in a list
                room_tiles = [info['location'] for info in state.values()
                             if 'class_inheritance' in info
                             and 'AreaTile' in info['class_inheritance']
                             and 'room_name' in info
                             and info['room_name'] == self._found_victim_logs[self._goal_vic]['room']]
                self._roomtiles = room_tiles
                objects = []
                # When the victim has to be carried by human and agent together, check whether human has arrived at the victim's location
                for info in state.values():
                    # When the victim has to be carried by human and agent together, check whether human has arrived at the victim's location
                    if 'class_inheritance' in info and 'CollectableBlock' in info['class_inheritance'] and 'critical' in \
                            info['obj_id'] and info['location'] in self._roomtiles or \
                            'class_inheritance' in info and 'CollectableBlock' in info[
                        'class_inheritance'] and 'mild' in info['obj_id'] and info[
                        'location'] in self._roomtiles and self._rescue == 'together' or \
                            self._goal_vic in self._found_victims and self._goal_vic in self._todo and len(
                        self._searched_rooms) == 0 and 'class_inheritance' in info and 'CollectableBlock' in info[
                        'class_inheritance'] and 'critical' in info['obj_id'] and info['location'] in self._roomtiles or \
                            self._goal_vic in self._found_victims and self._goal_vic in self._todo and len(
                        self._searched_rooms) == 0 and 'class_inheritance' in info and 'CollectableBlock' in info[
                        'class_inheritance'] and 'mild' in info['obj_id'] and info['location'] in self._roomtiles:
                        objects.append(info)

                        # HUMAN DID NOT ARRIVE - MILD
                        if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_RESCUE_MILD and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_arrive_timeout_lower_bound, trust_arrive_timeout_upper_bound):
                            # TRUST - Human did not arrive
                            print("[Mild victim] Did not arrive or act in time")
                            self._updateWillingness(-1)
                            self._updateCompetence(-1)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            # IGNORED - Continue
                            self._goal_vic = None
                            self._goal_loc = None
                            self._rescue = None
                            self._answered = True
                            self._waiting = False
                            self._moving = True
                            self._todo.append(self._recent_vic)
                            self._recent_vic = None
                            self._phase = Phase.FIND_NEXT_GOAL
                            return None, {}

                        # HUMAN DID NOT ARRIVE - CRITICAL
                        if self._trust_ongoing_check != OngoingTrustCheck.NONE and self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_RESCUE_CRITICAL and (self._curr_tick - self._trust_ongoing_check[0]) * tick_duration >= self.interpolWillingness(trust_arrive_timeout_lower_bound, trust_arrive_timeout_upper_bound):
                            # TRUST - Human did not arrive
                            print("[Critical victim] Did not arrive or act in time")
                            self._updateWillingness(-2)
                            self._updateCompetence(-2)
                            self._trust_ongoing_check = OngoingTrustCheck.NONE

                            # IGNORED - Continue
                            self._goal_vic = None
                            self._goal_loc = None
                            self._rescue = None
                            self._answered = True
                            self._waiting = False
                            self._moving = True
                            self._todo.append(self._recent_vic)
                            self._recent_vic = None
                            self._phase = Phase.FIND_NEXT_GOAL
                            return None, {}
                        
                        # Remain idle when the human has not arrived at the location
                        if not self._human_name in info['name']:
                            self._waiting = True
                            self._moving = False
                            return None, {}
                # Add the victim to the list of rescued victims when it has been picked up
                if len(objects) == 0 and 'critical' in self._goal_vic or len(
                        objects) == 0 and 'mild' in self._goal_vic and self._rescue == 'together':
                    if self._trust_ongoing_check != OngoingTrustCheck.NONE:
                        if self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_RESCUE_MILD:
                            print("[Mild victim] Rescued together") # Assuming the game can't let you drop it outside goal
                            self._updateCompetence(1)
                        elif self._trust_ongoing_check[2] == OngoingTrustCheck.WAITING_RESCUE_CRITICAL:
                            print("[Critical victim] Rescued together") # Assuming the game can't let you drop it outside goal
                            self._updateCompetence(2)
                    self._waiting = False
                    if self._goal_vic not in self._collected_victims:
                        self._collected_victims.append(self._goal_vic)
                    self._carrying_together = True
                    # Determine the next victim to rescue or search
                    self._phase = Phase.FIND_NEXT_GOAL
                # When rescuing mildly injured victims alone, pick the victim up and plan the path to the drop zone
                if 'mild' in self._goal_vic and self._rescue == 'alone':
                    self._phase = Phase.PLAN_PATH_TO_DROPPOINT
                    if self._goal_vic not in self._collected_victims:
                        self._collected_victims.append(self._goal_vic)
                    self._carrying = True
                    return CarryObject.__name__, {'object_id': self._found_victim_logs[self._goal_vic]['obj_id'],
                                                  'human_name': self._human_name}

            if Phase.PLAN_PATH_TO_DROPPOINT == self._phase:
                self._navigator.reset_full()
                # Plan the path to the drop zone
                self._navigator.add_waypoints([self._goal_loc])
                # Follow the path to the drop zone
                self._phase = Phase.FOLLOW_PATH_TO_DROPPOINT

            if Phase.FOLLOW_PATH_TO_DROPPOINT == self._phase:
                # Communicate that the agent is transporting a mildly injured victim alone to the drop zone
                if 'mild' in self._goal_vic and self._rescue == 'alone':
                    self._send_message('Transporting ' + self._goal_vic + ' to the drop zone.', 'RescueBot')
                self._state_tracker.update(state)
                # Follow the path to the drop zone
                action = self._navigator.get_move_action(self._state_tracker)
                if action is not None:
                    return action, {}
                # Drop the victim at the drop zone
                self._phase = Phase.DROP_VICTIM

            if Phase.DROP_VICTIM == self._phase:
                # Communicate that the agent delivered a mildly injured victim alone to the drop zone
                if 'mild' in self._goal_vic and self._rescue == 'alone':
                    self._send_message('Delivered ' + self._goal_vic + ' at the drop zone.', 'RescueBot')
                # Identify the next target victim to rescue
                self._phase = Phase.FIND_NEXT_GOAL
                self._rescue = None
                self._current_door = None
                self._tick = state['World']['nr_ticks']
                self._carrying = False
                # Drop the victim on the correct location on the drop zone
                return Drop.__name__, {'human_name': self._human_name}