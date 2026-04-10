# author: Franz Hempel
# created at: 2025-10-24
# company/institute: SweepMe! GmbH

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import curve_fit
from enum import Enum

from pysweepme.EmptyDeviceClass import EmptyDevice


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
    variables = ["Passed"]
    units = [""]
    # add your arguments by defining keys and default values in the dictionary below
    arguments = {
        "NanoTrak ID": "",
        "Mode": ["Horizontal", "Vertical", "2D"],
        "Input spot size": 10.,
        "Output spot size": 10.,
        "Maximum deviation": 25.,
        "Scan range": 21,
        "NanoTrak horizontal position": (),
        "NanoTrak vertical position": (),
    }
    execution = "process"  # Handle the NanoTrak reading after each measurement point

    def __init__(self) -> None:
        """Initialize class variables."""
        self.device_communication: dict[str, Any] = {}
        self.device_communication_key: str = ""

        self.mode: str = "Vertical"  # "Horizontal", "Vertical", or "2D"

        self.power_array: np.ndarray = np.array([])
        self.scan_range: int = 21
        self.positions_1d: np.ndarray = np.linspace(0, 10, self.scan_range)  # for 1D scans
        self.vertical_positions: np.ndarray = np.linspace(0, 10, self.scan_range)  # for 2D scans
        self.horizontal_positions: np.ndarray = np.linspace(0, 10, self.scan_range)  # for 2D scans

        self.original_vertical_position: float = 5.0
        self.original_horizontal_position: float = 5.0

        # Pass/Fail criteria
        self.maximum_deviation: float = 25.0  # maximum allowed deviation of Gauss maximum for successful coupling
        self.input_spot_size: float = 10.0  # in microns
        self.output_spot_size: float = 10.0  # in microns
        self.sigma_min: float = 0.0
        self.sigma_max: float = 0.0

    def main(self, **kwargs) -> bool:
        """Create an array of values according to the provided arguments."""
        self.mode = kwargs["Mode"]
        self.maximum_deviation = float(kwargs["Maximum deviation"])
        self.input_spot_size = float(kwargs["Input spot size"])
        self.output_spot_size = float(kwargs["Output spot size"])
        self.scan_range = int(kwargs["Scan range"])
        self.scan_direction = kwargs["Scan direction"]

        # Retrieve the NanoTrak driver instance from the device communication dictionary
        nanotrak_id = kwargs["NanoTrak ID"]
        device_communication_dict = EmptyDevice._device_communication
        key = f"NanoTrak {nanotrak_id}"
        if key not in device_communication_dict:
            msg = f"NanoTrak ID '{nanotrak_id}' not found in device communication dictionary."
            raise ValueError(msg)

        self.nanotrak: EmptyDevice = device_communication_dict[key]

        passed = False

        # Save Original Positions
        self.save_original_positions()


        if self.mode in ("Horizontal", "Vertical"):
            self.initialize_position_and_power_arrays("1D")
            # loop through horizontal positions, keeping vertical fixed, and save power readings

            # Scan 1D or 2D and save the power readings - requires power sensor?
            for n, position  in enumerate(self.positions_1d):
                horizontal_value = position if self.mode == "Horizontal" else self.original_horizontal_position
                vertical_value = position if self.mode == "Vertical" else self.original_vertical_position

                self.nanotrak.set_home_and_go_home(horizontal_value, vertical_value)  # will also latch
                self.power_array[n] = self.nanotrak.get_reading()  # TODO: use sensor instead

            passed = self.analyze_1d_power_array()

        elif self.mode == "2D":
            self.initialize_position_and_power_arrays("2D")
            # loop through horizontal and vertical positions and save power readings

            for i, vertical_value in enumerate(self.vertical_positions):
                for j, horizontal_value in enumerate(self.horizontal_positions):
                    self.nanotrak.set_home_and_go_home(horizontal_value, vertical_value)  # will also latch
                    self.power_array[i, j] = self.nanotrak.get_reading()  # TODO: use sensor instead

            passed = self.analyze_2d_power_array()

        # return to original position
        self.nanotrak.set_home_and_go_home(self.original_horizontal_position, self.original_vertical_position)

        # Optional: latch at original position
        if passed:
            self.nanotrak.track()
            self.nanotrak.wait_for_finish_tracking()
            self.nanotrak.latch()

        # return pass/fail
        return passed

    def save_original_positions(self) -> None:
        """Save the original NanoTrak positions."""
        self.original_horizontal_position, self.original_vertical_position = self.nanotrak.get_current_position()

    def initialize_position_and_power_arrays(self, mode: str = "1D") -> None:
        """Initialize position and power arrays for scanning."""
        if mode == "1D":
            self.power_array = np.zeros(self.scan_range)
            self.positions_1d = np.linspace(0, 10, self.scan_range)

        else:
            self.power_array = np.zeros((self.scan_range, self.scan_range))
            self.vertical_positions = np.linspace(0, 10, self.scan_range)
            self.horizontal_positions = np.linspace(0, 10, self.scan_range)

    def analyze_1d_power_array(self) -> bool:
        """Fit the 1D power array to find the best coupling position.

        Returns True if coupling is successful, False otherwise.
        """
        # Ensure flat 1D array for curve fitting
        power = np.asarray(self.power_array).ravel()

        # Normalize power to range from 0 to 1
        power = power - np.min(power)
        power = power / np.max(power)

        self.update_sigma_range()
        sigma_input = self.sigma_conversion(self.input_spot_size)
        sigma_output = self.sigma_conversion(self.output_spot_size)

        if self.scan_direction == "Horizontal":
            positions_um = self.horizontal_positions * 2
        else:
            positions_um = self.vertical_positions * 2

        try:
            # popt = Optimal parameters for the function, pcov = Covariance of the parameters
            center_position = positions_um[np.argmax(power)]
            popt, pcov = curve_fit(
                f=self.gaussian,
                xdata=positions_um,
                ydata=power,
                p0=[1, center_position, np.sqrt(sigma_input ** 2 + sigma_output ** 2)],
            )

        except Exception as e:
            return False

        return self.fit_is_valid(abs(popt[2]))

    def update_sigma_range(self) -> None:
        """Update the acceptable sigma range based on current spot sizes and maximum deviation."""
        sigma_conv = self.calculate_gaussian_width(self.input_spot_size, self.output_spot_size)
        self.sigma_min = sigma_conv * (1 - self.maximum_deviation / 100)
        self.sigma_max = sigma_conv * (1 + self.maximum_deviation / 100)

    @staticmethod
    def convert_voltage_to_dbm(voltage: float | np.ndarray) -> float | np.ndarray:
        """Convert voltage reading to dBm."""
        step = ((voltage - 3.5) * 22.17647059) - 20.1
        return 10 ** (step / 10)

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

    def fit_is_valid(self, sigma: float) -> bool:
        """Check if the fitted Gauss width is within the maximum deviation."""
        self.update_sigma_range()
        return self.sigma_min <= sigma <= self.sigma_max

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

    def calculate_gaussian_width(self, input_spot_size: float, output_spot_size: float) -> tuple:
        """
        Calculates the effective Gaussian width (MFD) of the convolution between
        the input and output modes, assuming both profiles are Gaussian.

        Assumptions:
            1. Both the input and the output mode fields have a Gaussian intensity profile.
            2. 1D case.
            3. Strongly guided waveguide approximation.

        Returns the sigma
        """
        sigma_input = self.sigma_conversion(input_spot_size)
        sigma_output = self.sigma_conversion(output_spot_size)

        # Calculate Gaussian profile for input and output
        x = np.linspace(0, 20, 1000)
        gauss_center = 10
        input_gaus = self.gaussian(x, 1, gauss_center, sigma_input)
        output_gaus = self.gaussian(x, 1, gauss_center, sigma_output)

        # Convolution of input and output Gaussian profiles
        conv_gaus = np.convolve(input_gaus, output_gaus, mode="same")
        conv_gaus /= np.max(conv_gaus)
        conv_gaus = conv_gaus ** 2

        # Fit the convolved Gaussian to extract the effective sigma
        popt, _ = curve_fit(
            self.gaussian,
            x,
            conv_gaus,
            p0=[1, gauss_center, np.sqrt(sigma_input ** 2 + sigma_output ** 2)]
        )
        sigma_conv = abs(popt[2])
        return sigma_conv

    @staticmethod
    def sigma_conversion(width: float) -> float:
        """Convert width to sigma (standard deviation) for Gaussian function."""
        return width / 4.0
