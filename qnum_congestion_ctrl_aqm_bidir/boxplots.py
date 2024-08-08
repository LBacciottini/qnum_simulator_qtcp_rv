import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def custom_boxplot(ax, data, mean, title, ylim, min_max=None, legend=False, x_labels=None):
    boxprops = dict(linestyle='-', linewidth=1., edgecolor='blue', facecolor='lightblue')
    whiskerprops = dict(color='black', linewidth=1.)
    capprops = dict(color='black', linewidth=1.)

    # make the median props as a solid black line
    medianprops = dict(color='black', linewidth=1.)

    # make the mean props as a dashed green line
    meanprops = dict(color='darkgreen', linestyle='--', linewidth=1.)

    if not isinstance(data, list):
        data = [data]
        mean = [mean]

    boxes = []
    outliers = []

    for i in range(len(data)):
        # extract outliers from the data (1 and 99 percentiles), i.e, first and last rows if min_max is None
        outliers.append(data[i].iloc[[0, -1]])

        # extract the box data (25th, 50th, 75th percentiles)
        box_data = data[i].iloc[2:5]

        # extract the whisker data (5th, 95th percentiles)
        whisker_data = data[i].iloc[[1, 6]]

        my_dict = {
            'med': box_data[1],
            'q1': box_data[0],
            'q3': box_data[2],
            'whislo': whisker_data[0],
            'whishi': whisker_data[1],
            'fliers': [],
            'mean': mean
        }

        boxes.append(my_dict)

    # Create boxplot manually
    ax.bxp(boxes, showmeans=False, meanline=True, widths=0.5,
        boxprops=boxprops, whiskerprops=whiskerprops,
        capprops=capprops, medianprops=medianprops,
        meanprops=meanprops, patch_artist=True)

    for i in range(len(mean)):
        label = "mean" if i == 0 else None
        ax.plot(i+1, mean[i], 'mx', label=label)

    # plot the outliers as white circles with a black border
    for i, outlier in enumerate(outliers):
        label = "1st, 99th" if i == 0 else None
        ax.plot([i+1, i+1], [outlier[0], outlier[1]], 'wo', markeredgecolor='black', label=label)

    if min_max is not None:

        if not isinstance(min_max, list):
            min_max = [min_max]

        for i, min_max_val in enumerate(min_max):
            label_min = "min" if i == 0 else None
            label_max = "max" if i == 0 else None
            # we plot the min and max values as well, min as a green triangle pointing down, max as a red triangle pointing up
            ax.plot(i+1, min_max_val[0], 'gv', label=label_min)
            ax.plot(i+1, min_max_val[1], 'r^', label=label_max)

            # check whether the min and max values are within the y limits
            # if not, we create a window within this plot to show them
            if min_max_val[0] < ylim[0]:
                # generate a rectangle to show the min value. put it right below the 1st percentile dot
                x_pos = 0.5*(2*i + 1)/len(data) - 0.05
                ax2 = ax.inset_axes([x_pos, 0.05, 0.1, 0.1])
                ax2.set_xticks([])
                # set the y-ticks to the min value and format it so that it has at most 2 decimal places
                min_2dp = float("{:.2f}".format(min_max_val[0]))
                ax2.set_yticks([min_2dp])

                ax2.plot(1, min_max_val[0], 'gv')
                ax2.set_xlim(0.5, 1.5)
                ax2.set_ylim(min_max_val[0] - min_max_val[0] * 0.1, min_max_val[0] + min_max_val[0] * 0.1)


            if min_max_val[1] > ylim[1]:
                # generate a rectangle to show the max value. put it right above the main plot
                x_pos = 0.5 * (2 * i + 1) / len(data) - 0.05
                ax3 = ax.inset_axes([x_pos, 0.85, 0.1, 0.1])
                ax3.set_xticks([])
                ax3.set_yticks([min_max_val[1]])
                ax3.plot(1, min_max_val[1], 'r^')
                ax3.set_xlim(0.5, 1.5)
                ax3.set_ylim(min_max_val[1] - min_max_val[1] * 0.1, min_max_val[1] + min_max_val[1] * 0.1)




    ax.set_title(title, fontsize=18, fontweight='bold', fontname='Arial')
    ax.set_ylim(ylim)
    # set y tick labels size
    ax.tick_params(axis='y', labelsize=15)
    # ax.set_xticklabels([y_label], fontsize=12)
    # remove xticks
    if x_labels is not None:
        ax.set_xticks([i + 1 for i in range(len(data))])
        ax.set_xticklabels(x_labels, fontsize=12)
    else:
        ax.set_xticks([])
    ax.grid(axis='y', linestyle='--', linewidth=0.5)

    if legend:
        # print a legend with font size 8
        ax.legend(loc="center right", fontsize=8)



if __name__ == "__main__":
    # Sample data
    data = {
        'Fidelity': [0.99, 0.98, 0.97, 0.96, 0.95],
        'Latency': [100, 150, 200, 250, 300] # milliseconds
    }

    """'Queue Size (non congested)': [0.1, 0.15, 0.2, 0.25, 0.3],  # num of requests
    'Queue Size (bottleneck link)': [10, 15, 20, 25, 30]  # num of requests"""

    csvs_lat = ["./out/latency_vector.csv", "./out2/latency_vector.csv"]
    csvs_fid = ["./out/fidelity_vector.csv", "./out2/fidelity_vector.csv"]
    x_labels = ["no RV", "with RV"]

    # replace the sample data with the data from the csv files
    df_list = []
    mean_fid_list = []
    min_max_fid_list = []
    mean_lat_list = []
    min_max_lat_list = []


    for i in range(len(csvs_lat)):
        df_latency = pd.read_csv(csvs_lat[i])
        # only keep the last half of the simulation
        df_latency = df_latency[df_latency["timestamp"] >= df_latency["timestamp"].max() / 2]
        df_latency["sample"] /= 1e3  # ms
        # compute boxplot data for latency, i.e., the 1st, 5th, 25th, 50th, 75th, 95th, 99th percentiles and the mean
        latency_boxplot_data = df_latency["sample"].describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        data['Latency'] = latency_boxplot_data[['1%', '5%', '25%', '50%', '75%', '95%', '99%']]

        df_fid = pd.read_csv(csvs_fid[i])
        # only keep the last half of the simulation
        df_fid = df_fid[df_fid["timestamp"] >= df_fid["timestamp"].max() / 2]
        # compute boxplot data for fidelity, i.e. the 1st, 5th, 25th, 50th, 75th, 95th, 99th percentiles and the mean
        fidelity_boxplot_data = df_fid["sample"].describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        data['Fidelity'] = fidelity_boxplot_data[['1%', '5%', '25%', '50%', '75%', '95%', '99%']]

        """df_queue_size_unc = pd.read_csv("./out/queue_size_free_vector.csv")
        # compute boxplot data for SKR, i.e. the 5th, 25th, 50th, 75th, 95th percentiles and the mean
        qs_unc_boxplot_data = df_queue_size_unc["sample"].describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        data['Queue Size (uncongested link)'] = qs_unc_boxplot_data[['1%', '5%', '25%', '50%', '75%', '95%', '99%']]
    
        df_queue = pd.read_csv("./out/queue_size_vector.csv")
        # compute boxplot data for throughput, i.e. the 5th, 25th, 50th, 75th, 95th percentiles and the mean
        queue_boxplot_data = df_queue["sample"].describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        data['Queue Size (bottleneck link)'] = queue_boxplot_data[['1%', '5%', '25%', '50%', '75%', '95%', '99%']]"""


        df = pd.DataFrame(data)
        df_list.append(df)

        mean_fid_list.append(df_fid["sample"].mean())
        min_max_fid_list.append((df_fid["sample"].min(), df_fid["sample"].max()))
        mean_lat_list.append(df_latency["sample"].mean())
        min_max_lat_list.append((df_latency["sample"].min(), df_latency["sample"].max()))

    # create custom boxplots from the percentiles we already have

    fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(4, 4))

    # Fidelity
    # create a nice boxplot for the fidelity from scratch, without using the built-in boxplot function
    # we use the percentiles we already have
    # the boxplot consists of the 25th, 50th, and 75th percentiles, the whiskers are the 5th and 95th percentiles
    # and the outliers are the 1st and 99th percentiles
    # we also show the mean as a dashed line
    custom_boxplot(axes[0], [df["Fidelity"] for df in df_list], mean_fid_list, 'Fidelity', (0.5, 1), min_max_fid_list, True, x_labels)

    # add grids so that every y-tick has a grid line
    axes[0].grid(axis='y', linestyle='--', linewidth=0.5)

    # Latency
    # create a nice boxplot for the latency from scratch, without using the built-in boxplot function
    # we use the percentiles we already have
    # the boxplot consists of the 25th, 50th, and 75th percentiles, the whiskers are the 5th and 95th percentiles
    # and the outliers are the 1st and 99th percentiles
    # we also show the mean as a dashed line
    custom_boxplot(axes[1], [df["Latency"] for df in df_list], mean_lat_list, 'Latency (ms)', (0, 60), min_max_lat_list, False, x_labels)

    # add grids so that every y-tick has a grid line
    axes[1].grid(axis='y', linestyle='--', linewidth=0.5)


    """# Creating faceted plots
    fig, axes = plt.subplots(nrows=2, ncols=2, figsize=(6, 6))
    # fig.suptitle('Box Plots')

    # Fidelity
    df.boxplot(column=['Fidelity'], ax=axes[0, 0])
    axes[0, 0].set_title('Fidelity')
    print(df["Fidelity"])

    # Latency
    df.boxplot(column=['Latency'], ax=axes[0, 1])
    axes[0, 1].set_title('Latency (ms)')"""

    """# QSU
    df.boxplot(column=['Queue Size (uncongested link)'], ax=axes[1, 0])
    axes[1, 0].set_title('Queue Size (uncongested link)')

    # QSB
    df.boxplot(column=['Queue Size (bottleneck link)'], ax=axes[1, 1])
    axes[1, 1].set_title('Queue Size (bottleneck link)')"""

    # now we also highlight the sample mean
    """mean_latency = df_latency["sample"].mean()
    mean_fidelity = df_fid["sample"].mean()
    # mean_qsu = df_queue_size_unc["sample"].mean()
    # mean_queue = df_queue["sample"].mean()

    # plot the mean as a red dot in the boxplot
    axes[0, 0].plot(1, mean_fidelity, 'ro', label="sample mean")
    # axes[0, 0].legend(loc="lower right")
    axes[0, 0].set_ylim(0.5, 1)
    axes[0, 1].plot(1, mean_latency, 'ro', label="sample mean")
    axes[0, 1].set_ylim(0, 50)"""
    # axes[0, 1].legend(loc="upper right")
    """axes[1, 0].plot(1, mean_qsu, 'ro', label="sample mean")
    axes[1, 0].axhline(y=10, color='magenta', linestyle='--', label="reference queue size")
    axes[1, 0].set_ylim(0, 40)
    # axes[1, 0].legend(loc="upper right")
    axes[1, 1].plot(1, mean_queue, 'ro', label="sample mean")
    axes[1, 1].axhline(y=10, color='magenta', linestyle='--', label="reference queue size")
    axes[1, 1].set_ylim(0, 40)
    # axes[1, 1].legend(loc="upper right")"""

    plt.tight_layout() # Adjust the layout to make room for the main title

    # save the plot and make sure it is not cut off
    plt.savefig("./out/boxplots.pdf", bbox_inches='tight')

    plt.show()

