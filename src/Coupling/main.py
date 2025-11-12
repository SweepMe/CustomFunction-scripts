# author: Franz Hempel
# created at: 2025-10-24
# company/institute: SweepMe! GmbH

from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit
from enum import Enum


class Phase(Enum):
    """Enum for the different phases of the coupling confirmation process."""

    INITIALIZE = 1
    SCANNING = 2
    FINALIZE = 3


class Main():
    """
    <h2>Confirm coupling</h2>
    
    Perform a 1D or 2D scan over positions and find the best coupling position.
    Intensity must be provided in linear scale, not in dBm.
    """

    # please define variables and units as returned by the function 'main'
    variables = ["Horizontal Position", "Vertical Position", "Operating", "Passed"]
    units = ["NT", "NT", "", ""]
    # add your arguments by defining keys and default values in the dictionary below
    arguments = {
        "Mode": ["1D", "2D"],
        "Maximum deviation": 25,
        "NanoTrak horizontal position": (),
        "NanoTrak vertical position": (),
        "Intensity": (),
    }
    execution = "process"  # Handle the NanoTrak reading after each measurement point

    def __init__(self) -> None:
        """Initialize class variables."""
        self.mode: str = "1D"  # "1D" or "2D"

        self.power_array: np.ndarray = np.array([])
        self.scan_range: int = 21
        self.vertical_positions: np.array = np.array([0])
        self.horizontal_positions: np.array = np.linspace(0, 10, self.scan_range)
        # TODO: double-check vertical and horizontal uses

        self.last_position_index: int | tuple = -1
        """Index of the last position scanned. Used to track progress."""

        self.original_vertical_position: float = 5.0
        self.original_horizontal_position: float = 5.0

        self.maximum_deviation: float = 25.0  # maximum allowed deviation of Gauss maximum for successful coupling

        self.phase: Phase = Phase.INITIALIZE

    def configure(self) -> None:
        """Create the 1D or 2D array of positions."""
        self.horizontal_positions = np.linspace(0, 10, self.scan_range)
        self.phase = Phase.INITIALIZE

        if self.mode == "1D":
            self.power_array = np.zeros(self.scan_range)
            self.vertical_positions = np.array([0.0])
            self.last_position_index = -1

        elif self.mode == "2D":
            self.power_array = np.zeros((self.scan_range, self.scan_range))
            self.vertical_positions = np.linspace(0, 10, self.scan_range)
            self.last_position_index = (-1, -1)

    def main(self, **kwargs) -> tuple:
        """Create an array of values according to the provided arguments."""
        self.mode = kwargs["Mode"]
        self.maximum_deviation = float(kwargs["Maximum deviation"])
        intensity = kwargs["Intensity"]
        operating = True
        passed = False

        if self.mode == "1D":
            # First call: save originals, switch to SCANNING and return first scan position
            if self.phase == Phase.INITIALIZE:
                self.original_vertical_position = float(kwargs["NanoTrak vertical position"])
                self.original_horizontal_position = float(kwargs["NanoTrak horizontal position"])
                print(f"First CFS call, saving original positions to {self.original_vertical_position} and {self.original_horizontal_position}.")

                self.phase = Phase.SCANNING
                self.last_position_index = 0
                next_horizontal_position = self.horizontal_positions[0]
                next_vertical_position = self.original_vertical_position

            # SCANNING: save intensity for the last returned position, then return next position
            elif self.phase == Phase.SCANNING:
                # save intensity measured at the previous position (if any)
                if isinstance(self.last_position_index, int) and self.last_position_index >= 0:
                    self.power_array[self.last_position_index] = intensity

                # if we just saved the last scan index, return home and prepare FINALIZE
                if self.last_position_index >= self.scan_range - 1:
                    self.phase = Phase.FINALIZE
                    next_horizontal_position = self.original_horizontal_position
                    next_vertical_position = self.original_vertical_position
                    # mark to avoid writing into power_array on the finalize call
                    self.last_position_index = -1
                else:
                    # advance to next scan index and return that position
                    self.last_position_index += 1
                    next_horizontal_position = self.horizontal_positions[self.last_position_index]
                    next_vertical_position = self.original_vertical_position

            # FINALIZE: run analysis and return passed with operating=False
            elif self.phase == Phase.FINALIZE:
                passed = self.analyze_1d_power_array()
                operating = False
                self.phase = Phase.INITIALIZE
                self.last_position_index = -1
                # return original position (instrument should be at original already)
                next_horizontal_position = self.original_horizontal_position
                next_vertical_position = self.original_vertical_position

        elif self.mode == "2D":
            # INITIALIZE: save originals, start scanning, return first scan position
            if self.phase == Phase.INITIALIZE:
                self.original_vertical_position = float(kwargs["NanoTrak vertical position"])
                self.original_horizontal_position = float(kwargs["NanoTrak horizontal position"])
                self.phase = Phase.SCANNING
                self.last_position_index = (0, 0)
                next_vertical_position = self.vertical_positions[0]
                next_horizontal_position = self.horizontal_positions[0]

            # SCANNING: save intensity for last returned position, then return next position
            elif self.phase == Phase.SCANNING:
                row, col = self.last_position_index
                # save intensity measured at the previous position (if any)
                if isinstance(row, int) and isinstance(col, int) and row >= 0 and col >= 0:
                    self.power_array[row, col] = intensity

                # if we just saved the last scan index, return home and prepare FINALIZE
                if row == self.scan_range - 1 and col == self.scan_range - 1:
                    self.phase = Phase.FINALIZE
                    next_vertical_position = self.original_vertical_position
                    next_horizontal_position = self.original_horizontal_position
                    # mark to avoid writing into power_array on the finalize call
                    self.last_position_index = (-1, -1)
                else:
                    # advance to next scan index and return that position
                    if col < self.scan_range - 1:
                        next_index = (row, col + 1)
                    else:
                        next_index = (row + 1, 0)
                    self.last_position_index = next_index
                    next_vertical_position = self.vertical_positions[next_index[0]]
                    next_horizontal_position = self.horizontal_positions[next_index[1]]

            # FINALIZE: run analysis and return passed with operating=False
            elif self.phase == Phase.FINALIZE:
                passed = self.analyze_2d_power_array()
                operating = False
                self.phase = Phase.INITIALIZE
                self.last_position_index = (-1, -1)
                # return original position (instrument should be at original already)
                next_vertical_position = self.original_vertical_position
                next_horizontal_position = self.original_horizontal_position

        else:
            msg = f"Invalid mode: {self.mode}. Use '1D' or '2D'."
            raise ValueError(msg)

        return next_horizontal_position, next_vertical_position, operating, passed

    def analyze_1d_power_array(self) -> bool:
        """Fit the 1D power array to find the best coupling position.

        Returns True if coupling is successful, False otherwise.
        """
        # power = self.convert_voltage_to_dbm(self.power_array)
        # Ensure flat 1D array for curve fitting
        power = np.asarray(self.power_array).ravel()

        try:
            # popt = Optimal parameters for the function, pcov = Covariance of the parameters
            popt, pcov = curve_fit(
                f=self.gaussian,
                xdata=self.horizontal_positions,
                ydata=power,
                p0=[0.01, 5, 4],
            )

        except Exception as e:
            return False

        return self.fit_is_valid(abs(popt[2]))

    @staticmethod
    def convert_voltage_to_dbm(voltage: float | np.ndarray) -> float | np.ndarray:
        """Convert voltage reading to dBm."""
        step = ((voltage - 3.5) * 22.17647059) - 20.1
        return 10**(step/10)  # ???

    @staticmethod
    def gaussian(x: np.ndarray, a: float, x0: float, sigma: float) -> np.ndarray:
        """Gaussian function for curve fitting.

        Args:
            x (np.ndarray): Input array.
            a (float): Amplitude of the Gaussian.
            x0 (float): Mean of the Gaussian.
            sigma (float): Standard deviation of the Gaussian.
        """
        return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))

    def fit_is_valid(self, position: float) -> bool:
        """Check if the fitted Gauss maximum is within the maximum deviation."""
        return 100 - self.maximum_deviation <= position <= 100 + self.maximum_deviation

    def analyze_2d_power_array(self) -> bool:
        """Fit the 2D power array to find the best coupling position.

        Returns True if coupling is successful, False otherwise.
        """
        # power_linear = self.convert_voltage_to_dbm(self.power_array)
        power_linear = np.asarray(self.power_array).ravel()

        initial_guess = [
            np.max(power_linear),
            np.mean(self.horizontal_positions),
            np.mean(self.vertical_positions),
            3,
            3,
            0,
            np.min(power_linear)
        ]
        xy_array = np.column_stack((self.horizontal_positions, self.vertical_positions))
        try:
            popt, pcov = curve_fit(
                self.gaus_2d,
                xy_array,
                power_linear,
                p0=initial_guess,
            )
        except Exception as e:
            return False

        return self.fit_is_valid(popt[1]) and self.fit_is_valid(popt[2])

    @staticmethod
    def gaus_2d(XY, amplitude, xo, yo, sigma_x, sigma_y, theta, offset) -> np.ndarray:
        """2D Gaussian function for curve fitting."""
        x, y = XY[:, 0], XY[:, 1]
        xo = float(xo)
        yo = float(yo)
        a = (np.cos(theta) ** 2) / (2 * sigma_x ** 2) + (np.sin(theta) ** 2) / (2 * sigma_y ** 2)
        b = -(np.sin(2 * theta)) / (4 * sigma_x ** 2) + (np.sin(2 * theta)) / (4 * sigma_y ** 2)
        c = (np.sin(theta) ** 2) / (2 * sigma_x ** 2) + (np.cos(theta) ** 2) / (2 * sigma_y ** 2)

        g = offset + amplitude * np.exp(- (a * ((x - xo) ** 2) + 2 * b * (x - xo) * (y - yo) + c * ((y - yo) ** 2)))
        return g.ravel()
