"""
plot the congestion window from ./out/congestion_window_vector.csv as a function of time (ms)
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
    # ax.set_ylabel("Congestion Window Size")
    ax.set_ylabel("Latency (ms)", color="red")
    ax.set_title("Latency and Throughput")
    ax.set_ylim(0, 100)

    # make the y-axis labels be at the same x position
    ax.yaxis.set_label_coords(x=-0.06, y=0.5)
    ax2.yaxis.set_label_coords(x=-0.06, y=0.5)

    # read also the file "latency_vector.csv" and plot a moving average of latency as a function of time in the same plot
    df_lat = pd.read_csv("./out/latency_vector.csv")

    # Compute the sliding window average
    window_size_time_units = 80000

    # create a new column with the sliding window index
    df_lat["sw_index"] = df_lat["timestamp"] // window_size_time_units

    # compute the sliding window average
    sw_avg = df_lat.groupby("sw_index").mean()

    # divide the timestamp and the sample by 1e3 to have ms
    sw_avg["timestamp"] /= 1e3
    sw_avg["sample"] /= 1e3

    # ax2 = ax.twinx()
    ax.plot(sw_avg["timestamp"], sw_avg["sample"], color="red", label="latency")
    # ax.set_ylabel("Latency (ms)")

    cur_flows = 4
    delete_phase = False
    # create a colormap for the background
    colors = {4: "blue", 10: "yellow", 16: "red"}
    for i in range(0, 48000, 8000):
        ax.axvline(x=i, color='black', linestyle=':', alpha=0.5)
        ax2.axvline(x=i, color='black', linestyle=':', alpha=0.5)
        # add some text next to the line saying "2 flows added" at the top
        ax.text(i + 1000, 80, f"{cur_flows} flows", rotation=0, fontsize=10)

        # add a colored background
        ax.axvspan(i, i + 8000, color=colors[cur_flows], alpha=0.1)
        ax2.axvspan(i, i + 8000, color=colors[cur_flows], alpha=0.1)

        if cur_flows == 16:
            delete_phase = True
        if cur_flows == 4:
            delete_phase = False
        if delete_phase:
            cur_flows -= 6
        else:
            cur_flows += 6


    # read the throughput file and plot the throughput as a sliding window average
    df_irg = pd.read_csv("./out/throughput_vector.csv")
    window_size_time_units *= 5
    # sw_avg_irg = pd.Series([df_irg[(df_irg["timestamp"] >= t - window_size_time_units) & (df_irg["timestamp"] < t)]["sample"].mean() for t in df_irg["timestamp"]])
    sw_avg_irg = pd.Series([df_irg[(df_irg["timestamp"] >= t - window_size_time_units) & (df_irg["timestamp"] < t)]["sample"].count() for t in df_irg["timestamp"]])
    sw_avg_irg /= window_size_time_units # pairs per us
    sw_avg_irg *= 1e3  # pairs per ms

    df_irg["timestamp"] /= 1e3

    ax2.plot(df_irg["timestamp"], sw_avg_irg, color="blue", label="E2E Throughput")
    # ax2.set_ylabel("Inter-Request Gap (IRG) (ms)", color="blue")
    ax2.set_ylabel("Throughput (pairs/ms)", color="blue")
    # ax2.set_ylim(0, 4)

    """
    # we add a third axis to plot the throughput, again as a moving average
    throughput_window_size_time_units = 1000
    ax3 = ax.twinx()
    df_throughput = pd.read_csv("./out/throughput_vector.csv")
    df_throughput["sw_index"] = df_throughput["timestamp"] // throughput_window_size_time_units
    sw_avg_throughput = df_throughput.groupby("sw_index").count()
    sw_avg_throughput["sample"] /= throughput_window_size_time_units  # pairs per ms

    ax3.plot(sw_avg_throughput.index, sw_avg_throughput["sample"], color="green", label="throughput")
    """
    """
    df_fid = sw_avg
    df_fid["fid"] = df_fid.apply(lambda row: compute_fid(row["sample"], 0.01), axis=1)
    ax2 = ax.twinx()
    ax2.plot(df_fid["timestamp"], df_fid["fid"], color="green", label="Fidelity")
    ax2.set_ylabel("Fidelity")
    """


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
    plt.savefig("./out/latency_dynamic.pdf")

    plt.show()

