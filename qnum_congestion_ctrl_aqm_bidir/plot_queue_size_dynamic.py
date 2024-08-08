"""
Read the file "queue_size_vector.csv" and plot the queue size as a function of time
"""

import pandas as pd
import matplotlib.pyplot as plt

if __name__ == "__main__":
    df = pd.read_csv("./out/queue_size_vector.csv")

    fig, axs = plt.subplots(2, sharex=True)
    ax = axs[0]
    ax2 = axs[1]

    ax2.set_xlabel("Time (ms)")

    # now we want to plot as a sliding window average
    window_size_time_units = 10000
    # every point in the plot is the average of all samples in the window
    # we can't use directly group by because the same sample may be in multiple adjacent windows
    # so, for every row in df, we compute the average of all samples in the window
    # we use a list comprehension to do that
    sw_avg = pd.Series([df[(df["timestamp"] >= t - window_size_time_units) & (df["timestamp"] < t)]["sample"].mean() for t in df["timestamp"]])

    df["timestamp"] = df["timestamp"] / 1e3  # convert to ms

    # multiply the sample column by 0.04
    # sw_avg *= 0.04

    ax.plot(df["timestamp"], sw_avg, label="queue size", color="purple")

    ax.set_ylabel("Queue Size (# requests)", color="purple")

    # also plot a horizontal green dashed line at the reference queue size set to 20
    ax.axhline(y=10, color='magenta', linestyle='--', label="reference queue size")

    cur_flows = 4
    delete_phase = False
    # create a colormap for the background
    colors = {4: "blue", 10: "yellow", 16: "red"}
    for i in range(0, 48000, 8000):
        ax.axvline(x=i, color='black', linestyle=':', alpha=0.5)
        ax2.axvline(x=i, color='black', linestyle=':', alpha=0.5)
        # add some text next to the line saying "2 flows added" at the top
        ax.text(i + 1000, 45, f"{cur_flows} flows", rotation=0, fontsize=10)

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

    # read the IRG file and plot the Inter-Request Gap (IRG) on the same plot but on a different axis
    df_irg = pd.read_csv("./out/IRG_vector.csv")
    window_size_time_units = 50000
    sw_avg_irg = pd.Series([df_irg[(df_irg["timestamp"] >= t - window_size_time_units) & (df_irg["timestamp"] < t)]["sample"].mean() for t in df_irg["timestamp"]])

    df_irg["timestamp"] /= 1e3

    # set y axis in ms
    sw_avg_irg /= 1e3

    ax2.plot(df_irg["timestamp"], sw_avg_irg, color="green", label="IRG (flow 0)")
    # ax2.set_ylabel("Inter-Request Gap (IRG) (ms)", color="blue")
    ax2.set_ylabel("Inter-Request Gap (ms)", color="green")

    # set the maximum value for the y-axis
    # ax2.set_ylim(0, 16)

    ax.set_title("Queue size and IRG (flow 0)")

    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()

    ax.legend(lines, labels, loc="upper right")
    # ax2.legend(lines2, labels2, loc="lower right")

    plt.tight_layout()

    plt.show()

    # Save the figure
    fig.savefig("./out/queue_size.pdf")

