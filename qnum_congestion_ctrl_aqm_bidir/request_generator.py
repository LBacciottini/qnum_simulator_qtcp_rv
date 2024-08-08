"""
Stochastic process that generates requests for a flow according to a Poisson process.
"""

class RequestGenerator:
    """
    Stochastic process that generates requests for a flow according to a Poisson process.

    Parameters
    ----------
    arrival_rate : float
        Arrival rate of the Poisson process (1/ms)
    rng : :class:`~omnetpypy.utilities.MultiRandom`
        Random number generator
    rng_index : int
        Index of the random number generator to use

    """
    def __init__(self, arrival_rate, rng, rng_index):
        self.arrival_rate = arrival_rate  # packets per second
        self.arrival_rate_us = arrival_rate/1e6  # packets per us
        self.rng = rng
        self.rng_index = rng_index

    def next_request_gap(self):
        """
        Generate the time of the next request

        Parameters
        ----------
        current_time : float
            Current time

        Returns
        -------
        float
            Time of the next request

        """
        rnd = self.rng.expovariate(self.arrival_rate_us, self.rng_index)
        return rnd
