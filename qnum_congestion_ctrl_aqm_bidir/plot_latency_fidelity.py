"""
plot the congestion window from ./out3/congestion_window_vector.csv as a function of time (ms)
there is only one flow
"""
import math

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def compute_fid(latency, gamma):
    """
    Compute the flow id from the latency and the gamma parameter
    """
    return 0.5 + 0.5*math.exp(-2*gamma*latency)

if __name__ == "__main__":

    fig, axs = plt.subplots(2, sharex=True)
    ax = axs[0]
    ax2 = axs[1]
    """
    ax.plot(df["timestamp"], df["sample"], label="congestion window")
    """

    ax2.set_xlabel("Time (ms)")
    ax2.set_ylabel("Fidelity", color="blue")
    ax.set_ylabel("Latency (ms)", color="red")
    ax.set_title("Latency and Fidelity")
    ax.set_ylim(0, 40)

    # make the y-axis labels be at the same x position
    ax.yaxis.set_label_coords(x=-0.06, y=0.5)
    ax2.yaxis.set_label_coords(x=-0.06, y=0.5)

    # read also the file "latency_vector.csv" and plot a moving average of latency as a function of time in the same plot
    df_lat = pd.read_csv("./out3/latency_vector.csv")

    # Compute the sliding window average
    window_size_time_units = 5000

    # create a new column with the sliding window index
    df_lat["sw_index"] = df_lat["timestamp"] // window_size_time_units

    # compute the sliding window average
    sw_avg = pd.Series(
        [df_lat[(df_lat["timestamp"] >= t - window_size_time_units) & (df_lat["timestamp"] < t)]["sample"].mean() for t
         in df_lat["timestamp"]])

    # divide the timestamp by 1e3 to have ms
    df_lat["timestamp"] /= 1e3
    sw_avg /= 1e3

    # ax2 = ax.twinx()
    ax.plot(df_lat["timestamp"], sw_avg, color="red", label="latency")
    # ax.set_ylabel("Latency (ms)")

    # still on ax2 print the average secret key rate for the second half of the simulation
    ax.axhline(y=sw_avg[sw_avg.size // 2:].mean(), color='red', linestyle='--',
                label="AVG latency at steady state")

    # read also the file "latency_vector.csv" and plot a moving average of latency as a function of time in the same plot
    df_fid = pd.read_csv("./out3/fidelity_vector.csv")

    # Compute the sliding window average
    window_size_time_units = 25000

    # create a new column with the sliding window index
    df_fid["sw_index"] = df_fid["timestamp"] // window_size_time_units

    # compute the sliding window average
    sw_avg = pd.Series(
        [df_fid[(df_fid["timestamp"] >= t - window_size_time_units) & (df_fid["timestamp"] < t)]["sample"].mean() for t
         in df_fid["timestamp"]])

    # divide the timestamp by 1e3 to have ms
    df_fid["timestamp"] /= 1e3

    ax2.set_ylim(0.4, 1)

    # ax2 = ax.twinx()
    ax2.plot(df_fid["timestamp"], sw_avg, color="blue", label="E2E Fidelity")
    # ax.set_ylabel("Latency (ms)")

    # still on ax2 print the average secret key rate for the second half of the simulation
    ax2.axhline(y=sw_avg[sw_avg.size // 2:].mean(), color='blue', linestyle='--',
               label="AVG E2E FID at steady state")

    # print the legends within the axis

    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    # lines3, labels3 = ax3.get_legend_handles_labels()
    # ax2.legend(lines + lines2, labels + labels2, loc="upper right")

    # print legend in the axis box
    # ax.legend(lines, labels, loc="best")
    # ax2.legend(lines2, labels2, loc="best")

    # adjust plot size
    fig.tight_layout()

    # save the plot
    plt.savefig("./out3/latency_fidelity.pdf")

    plt.show()

