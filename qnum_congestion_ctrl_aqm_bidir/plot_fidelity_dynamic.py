"""
We plot here fidelity and secret key rate in the same way as we did for latency and throughput in the previous notebook.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

if __name__ == "__main__":
    fig, axs = plt.subplots(2, sharex=True)
    ax = axs[0]
    ax2 = axs[1]
    """
    ax.plot(df["timestamp"], df["sample"], label="congestion window")
    """

    ax2.set_xlabel("Time (ms)")
    # ax.set_ylabel("Congestion Window Size")
    ax.set_ylabel("Fidelity", color="red")
    ax.set_title("Fidelity and Secret Key Rate")

    # make the y-axis labels be at the same x position
    ax.yaxis.set_label_coords(x=-0.09, y=0.5)
    ax2.yaxis.set_label_coords(x=-0.09, y=0.5)

    # read also the file "latency_vector.csv" and plot a moving average of latency as a function of time in the same plot
    df_fid = pd.read_csv("./out/fidelity_vector.csv")

    # Compute the sliding window average
    window_size_time_units = 40000

    # create a new column with the sliding window index
    df_fid["sw_index"] = df_fid["timestamp"] // window_size_time_units

    # compute the sliding window average
    sw_avg = df_fid.groupby("sw_index").mean()

    # divide the timestamp by 1e3 to have ms
    sw_avg["timestamp"] /= 1e3

    ax.set_ylim(0.4, 1)

    # ax2 = ax.twinx()
    ax.plot(sw_avg["timestamp"], sw_avg["sample"], color="red", label="E2E Fidelity")
    # ax.set_ylabel("Latency (ms)")

    cur_flows = 4
    delete_phase = False
    # create a colormap for the background
    colors = {4: "blue", 10: "yellow", 16: "red"}
    for i in range(0, 48000, 8000):
        ax.axvline(x=i, color='black', linestyle=':', alpha=0.5)
        ax2.axvline(x=i, color='black', linestyle=':', alpha=0.5)
        # add some text next to the line saying "2 flows added" at the top
        ax.text(i + 1000, 0.5, f"{cur_flows} flows", rotation=0, fontsize=10)

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

    # we obtain the secret key rate from df_fid by computing the secret key fraction for each sample
    # the secret key fraction is 1 - 2h(2(1-f)/3), where h is the binary entropy function and f is the fidelity
    df_skr = df_fid.copy()

    def binary_entropy(x):
        return -x * np.log2(x) - (1-x) * np.log2(1-x)

    df_skr["sample"] = 1 - 2 * binary_entropy(2 * (1 - df_skr["sample"]) / 3)
    # replace negative values with 0
    df_skr["sample"] = df_skr["sample"].clip(lower=0)

    # read the IRG file and plot the Inter-Request Gap (IRG) on the same plot but on a different axis
    window_size_time_units *= 5
    # sw_avg_irg = pd.Series([df_irg[(df_irg["timestamp"] >= t - window_size_time_units) & (df_irg["timestamp"] < t)]["sample"].mean() for t in df_irg["timestamp"]])
    sw_avg_skr = pd.Series(
        [df_skr[(df_skr["timestamp"] >= t - window_size_time_units) & (df_skr["timestamp"] < t)]["sample"].sum() for t
         in df_skr["timestamp"]])
    sw_avg_skr /= window_size_time_units  # pairs per us
    sw_avg_skr *= 1e3  # pairs per ms

    df_skr["timestamp"] /= 1e3

    ax2.plot(df_skr["timestamp"], sw_avg_skr, color="blue", label="E2E Secret Key Rate")
    # ax2.set_ylabel("Inter-Request Gap (IRG) (ms)", color="blue")
    ax2.set_ylabel("E2E Secret Key Rate (bits/ms)", color="blue")
    # ax2.set_ylim(0, 2)

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

    plt.show()

    # save the figure
    fig.savefig("./out/fidelity_secret_key_rate.pdf")