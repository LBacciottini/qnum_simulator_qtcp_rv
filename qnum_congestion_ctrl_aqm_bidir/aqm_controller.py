"""
This module implements the PI controller for the AQM algorithm.
"""
from omnetpypy import sim_log


class PIController:

    def __init__(self):
        self.alpha = None
        self.beta = None
        self.q_ref = None

        self.q_old = 0
        self.p_old = 0

        self.q = 0
        self.p = 0

    def update(self, q):
        self.q = q
        self.p = self.alpha * (self.q - self.q_ref) - self.beta * (self.q_old - self.q_ref) + self.p_old
        # print(f"q_ref={self.q_ref}, q={self.q}, p={self.p}, p_old={self.p_old}, q_old={self.q_old}")
        self.q_old = self.q
        self.p_old = self.p

    def get_marking_probability(self):
        return self.p
        # return 0.

    def set_parameters(self, R_plus, C, N_minus, q_ref):
        """
        Set the a,b parameters for the PI controller from R_plus, C, N_minus, T

        Parameters
        ----------
        R_plus : float
            The maximum Round Trip Time (RTT) in seconds for which the PI controller is stable
        C : float
            The channel capacity in LLE attempts per second
        N_minus : float
            The minimum number of TCP-like flows passing through the link
        q_ref : float
            The reference queue size in (avg) LLE attempts

        Returns
        -------
        T : float
            The time interval in seconds for the PI controller sampling
        """

        omega_g = 2*N_minus/(R_plus*R_plus*C)
        assert omega_g < 0.05/R_plus, "The PI controller could not be stable"
        p_queue = 1/R_plus

        T = 1/(omega_g*100)

        K_PI = (complex(0, omega_g)/p_queue + 1)/((R_plus*C)**3/(2*N_minus)**2)
        # turn K_PI into a real number by taking the module
        K_PI = abs(K_PI)*omega_g*100  # TODO: remove the *10

        assert 1-omega_g*T > 0, "The PI controller could not be stable"
        self.alpha = K_PI/omega_g
        self.beta = self.alpha*(1-omega_g*T)
        self.q_ref = q_ref

        sim_log.debug(f"PI controller parameters: alpha={self.alpha}, beta={self.beta}, q_ref={q_ref}, K_PI={K_PI},"
                      f"omega_g={omega_g}, T={T}")

        return T
