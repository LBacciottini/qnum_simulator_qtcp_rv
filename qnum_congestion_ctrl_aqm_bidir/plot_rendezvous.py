"""
Plot the rendezvous node index as a nice-looking histogram
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

if __name__ == "__main__":
    fig, ax = plt.subplots()
    ax.set_title("Rendezvous Analysis")
    ax.set_xlabel("Rendezvous Node")
    ax.set_ylabel("Probability")
    df = pd.read_csv("./out2/rendezvous_node_vector.csv")
    # plot the histogram with a column for every value in df["sample"]
    # the height of the column is the number of occurrences of that value in df["sample"]

    # get the distinct values of the rendezvous node index
    distinct_values = df["sample"].unique()
    # sort the values
    distinct_values.sort()
    # compute the histogram
    hist = [df[df["sample"] == val].shape[0] for val in distinct_values]

    # normalize the histogram
    hist = np.array(hist) / np.sum(hist)

    # plot the histogram
    ax.bar(distinct_values, hist)

    plt.show()

    # save the figure as pdf
    fig.savefig("./out2/rendezvous_node_bars.pdf")
