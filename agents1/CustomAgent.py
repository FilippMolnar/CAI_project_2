from agents1.OfficialAgent import BaselineAgent

class CustomAgent(BaselineAgent):

    def __init__(self, slowdown, condition, name, folder):
        super().__init__(slowdown, condition, name, folder)
        self._trust_processed_messages = 0 # Number of processed messages the last time trust was updated
        self._trust_ongoing_checks = [] # Past signalling that needs to be cross-checked with world information to update trust
        self._trust_willingness_total = {} # Total wilingness score assigned to other agents
        self._trust_competency_total = {} # Total competency score assigned to other agents
        self._trust_wilingness_interactions_count = {} # Dictionary of #interactions with other agents influencing wilingness
        self._trust_competency_interactions_count = {} # Dictionary of #interactions with other agents influencing competency

    def _trustBelief(self, members, trustBeliefs, folder, receivedMessages):
        # Update the trust value based on for example the received messages
        for message in receivedMessages:
            # Increase agent trust in a team member that rescued a victim
            if 'Collect' in message:
                print("Called _trustBelief")
                trustBeliefs[self._human_name]['competence'] += 0.10
                # Restrict the competence belief to a range of -1 to 1
                trustBeliefs[self._human_name]['competence'] = np.clip(trustBeliefs[self._human_name]['competence'], -1,
                                                                       1)
        # Save current trust belief values so we can later use and retrieve them to add to a csv file with all the logged trust belief values
        # with open(folder + '/beliefs/currentTrustBelief.csv', mode='w') as csv_file:
        #     csv_writer = csv.writer(csv_file, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        #     csv_writer.writerow(['name', 'competence', 'willingness'])
        #     csv_writer.writerow([self._human_name, trustBeliefs[self._human_name]['competence'],
        #                          trustBeliefs[self._human_name]['willingness']])
                
        # Tasks:
                # 1. Need to only use new messages to update willingness and competence
                # 2. Need to wait and see if messages correspond to the actual board state

            # Copy methods from OfficialAgent that will be modified. E.g. the decide_on_actions

        return trustBeliefs