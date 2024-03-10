import matplotlib.pyplot as plt
import csv

# Example data

humans={}
name = 'eve'
with open('./logs/logWillCom.csv', mode='r') as f:
    reader = csv.reader(f) 
    for r in reader:
        if len(r) <= 0:
            continue
        row = r[0].split(';')
        if row[0] in humans:
            humans[row[0]]['competence'] += [round(float(row[1]),2)]
            humans[row[0]]['willingness'] += [round(float(row[2]),2)]
        else:
            humans[row[0]] = {}
            humans[row[0]]['competence'] = [round(float(row[1]),2)]
            humans[row[0]]['willingness'] = [round(float(row[2]),2)]

x_values = list(range(0, len(humans[name]['willingness'])))
y_values = humans[name]['willingness']

# Plotting the values

plt.plot(list(range(0, len(humans[name]['willingness']))), humans[name]['willingness'], label='willingness')
plt.plot(list(range(0, len(humans[name]['competence']))), humans[name]['competence'], label='competence')

# Adding labels and title
plt.xlabel('rounds')
plt.ylabel('score')
plt.title(name.capitalize())

# Displaying legend (optional)
plt.legend()

# Display the plot
plt.show()