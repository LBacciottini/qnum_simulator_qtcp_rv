"""
Print a plot of the queuing_time_vector.csv file as a sliding window average with window size 1000 time units.
"""

import pandas as pd
import matplotlib.pyplot as plt

# Load the data
df = pd.read_csv("./out/queuing_time_vector.csv")

# Compute the sliding window average
window_size_time_units = 100

# create a new column with the sliding window index
df["sw_index"] = df["timestamp"] // window_size_time_units

# compute the sliding window average
sw_avg = df.groupby("sw_index").mean()

# divide the timestamp and the sample by 1e3 to have ms
sw_avg["timestamp"] /= 1e3
sw_avg["sample"] /= 1e3

# plot the sliding window average as a function of timestamp
plt.plot(sw_avg["timestamp"], sw_avg["sample"])
plt.xlabel("Time (ms)")
plt.ylabel("Queuing time (ms)")
plt.title("Moving average of queuing time")

plt.show()
