# author: Franz Hempel
# created at: 2025-10-24
# company/institute: SweepMe! GmbH

from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit


class Main():
    """
    <h2>Confirm coupling</h2>
    
    Perform a 1D or 2D scan over positions and find the best coupling position.
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
        "NanoTrak Reading": (),
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

    def configure(self) -> None:
        """Create the 1D or 2D array of positions."""
        self.horizontal_positions = np.linspace(0, 10, self.scan_range)

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
        reading = kwargs["NanoTrak Reading"]
        operating = True
        passed = False

        if self.mode == "1D":
            if self.last_position_index < 0:
                # First call, save first home position, do not save reading yet
                # TODO: check if float conversion is necessary
                self.original_vertical_position = float(kwargs["NanoTrak vertical position"])
                self.original_horizontal_position = float(kwargs["NanoTrak horizontal position"])
                print(f"First CFS call, saving original positions to {self.original_vertical_position} and {self.original_horizontal_position}.")

            else:
                # All other calls, save reading at last position
                self.power_array[self.last_position_index] = reading

            next_position_index = self.last_position_index + 1

            if next_position_index >= self.scan_range - 1:
                passed = self.analyze_1d_power_array()
                operating = False
                self.last_position_index = -1
                next_vertical_position = self.original_vertical_position
                next_horizontal_position = self.original_horizontal_position
            else:
                self.last_position_index = next_position_index
                next_horizontal_position = self.horizontal_positions[next_position_index]
                next_vertical_position = self.original_vertical_position

        elif self.mode == "2D":
            row, col = self.last_position_index
            if (row, col) == (-1, -1):
                # First call, save first home position, do not save reading yet
                self.original_vertical_position = float(kwargs["NanoTrak vertical position"])
                self.original_horizontal_position = float(kwargs["NanoTrak horizontal position"])
            else:
                # All other calls, save reading at last position
                self.power_array[row, col] = reading

            # increase index
            if col < self.scan_range - 1:
                next_position_index = (row, col + 1)
            else:
                next_position_index = (row + 1, 0)

            if row >= self.scan_range:
                # finished
                operating = False
                passed = self.analyze_2d_power_array()
                self.last_position_index = (-1, -1)
                next_vertical_position = self.original_vertical_position
                next_horizontal_position = self.original_horizontal_position
            else:
                self.last_position_index = next_position_index
                next_vertical_position = self.vertical_positions[next_position_index[0]]
                next_horizontal_position = self.horizontal_positions[next_position_index[1]]

        else:
            msg = f"Invalid mode: {self.mode}. Use '1D' or '2D'."
            raise ValueError(msg)

        return next_vertical_position, next_horizontal_position, operating, passed

    def analyze_1d_power_array(self) -> bool:
        """Fit the 1D power array to find the best coupling position.

        Returns True if coupling is successful, False otherwise.
        """
        power = self.convert_voltage_to_dbm(self.power_array)
        # Ensure flat 1D array for curve fitting
        power = np.asarray(power).ravel()

        try:
            # popt = Optimal parameters for the function, pcov = Covariance of the parameters
            popt, pcov = curve_fit(
                f=self.gaussian,
                xdata=self.vertical_positions,
                ydata=power,
                p0=[0.01, 5, 4],
            )

        except Exception as e:
            return False

        if self.fit_is_valid(abs(popt[2])):
            return True

        return False

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
        power_linear = self.convert_voltage_to_dbm(self.power_array)
        power_linear = np.asarray(power_linear).ravel()

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

        if self.fit_is_valid(popt[1]) and self.fit_is_valid(popt[2]):
                return True

        return False

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
