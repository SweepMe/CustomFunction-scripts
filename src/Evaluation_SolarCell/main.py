# author: Franz Hempel
# created at: 2026-03-31

import numpy as np


class Main():

    """
    <h2>Solar Cell IV Curve Analysis</h2>
    <p>
    Extracts photovoltaic figures of merit from an illuminated IV curve measured by one SMU.
    Optionally a dark IV curve (from the same SMU) can be provided to compute additional
    parameters. The dark curve may have different voltage points than the light curve;
    interpolation is used where needed.
    </p>
    <h3>Outputs</h3>
    <ul>
    <li><b>I_sc</b>: Short-circuit current — interpolated at V = 0</li>
    <li><b>V_oc</b>: Open-circuit voltage — interpolated at I = 0</li>
    <li><b>P_mpp</b>: Maximum output power |V &times; I| in the power-generating quadrant</li>
    <li><b>V_mpp</b>: Voltage at the maximum power point</li>
    <li><b>I_mpp</b>: Current at the maximum power point</li>
    <li><b>FF</b>: Fill factor = P_mpp / (|I_sc| &times; |V_oc|)</li>
    <li><b>sat</b>: Saturation = I_light at most-negative voltage / I_sc</li>
    <li><b>Id_mpp</b>: Dark current interpolated at V_mpp (nan if no dark data or V_mpp
        outside dark voltage range)</li>
    <li><b>sat_ph</b>: Photocurrent saturation = (I_light &minus; I_dark) at most-negative
        voltage / I_sc (nan if no dark data or voltage outside dark range)</li>
    </ul>
    <p>
    Both sign conventions are supported (I_sc positive or negative). Leave I_dark and V_dark
    unconnected if no dark measurement is available.
    </p>
    """

    variables = ["I_sc", "V_oc", "P_mpp", "V_mpp", "I_mpp", "FF", "Sat", "Id_mpp", "Sat_ph"]
    units = ["A", "V", "W", "V", "A", "", "", "A", ""]

    arguments = {
        "I_light": (),
        "V_light": (),
        "I_dark": (),
        "V_dark": (),
    }

    def main(self, **kwargs):

        I_light = np.array(kwargs["I_light"], dtype=float)
        V_light = np.array(kwargs["V_light"], dtype=float)
        I_dark_raw = np.array(kwargs["I_dark"], dtype=float)
        V_dark_raw = np.array(kwargs["V_dark"], dtype=float)

        nan = float("nan")
        nan_result = [nan] * 9

        if len(I_light) < 2 or len(V_light) < 2:
            return nan_result

        # Sort light data by voltage ascending
        sort_idx = np.argsort(V_light)
        V = V_light[sort_idx]
        I = I_light[sort_idx]

        # Sort dark data if provided
        has_dark = len(I_dark_raw) >= 2 and len(V_dark_raw) >= 2
        if has_dark:
            dark_sort = np.argsort(V_dark_raw)
            V_dark = V_dark_raw[dark_sort]
            I_dark = I_dark_raw[dark_sort]

        # I_sc: interpolate at V = 0 (voltage range must include 0)
        if V[0] > 0 or V[-1] < 0:
            return nan_result

        I_sc = np.interp(0.0, V, I)
        if I_sc == 0:
            return [I_sc, nan, nan, nan, nan, nan, nan, nan, nan]

        # V_oc: linear interpolation across first zero crossing of I
        sign_changes = np.where(np.diff(np.sign(I)))[0]
        if len(sign_changes) == 0:
            V_oc = nan
        else:
            i = sign_changes[0]
            dI = I[i + 1] - I[i]
            V_oc = V[i] + (V[i + 1] - V[i]) * (-I[i]) / dI if dI != 0 else nan

        # Power-generating quadrant and MPP
        P_mpp, V_mpp, I_mpp, FF = nan, nan, nan, nan
        if not np.isnan(V_oc):
            # Power quadrant: V between 0 and V_oc, current opposite sign to V_oc
            mask = (V * np.sign(V_oc) > 0) & (I * np.sign(I_sc) > 0)
            if np.any(mask):
                P_quad = np.abs(V[mask] * I[mask])
                idx_mpp = int(np.argmax(P_quad))
                V_mpp = V[mask][idx_mpp]
                I_mpp = I[mask][idx_mpp]
                P_mpp = P_quad[idx_mpp]
                FF = P_mpp / (np.abs(I_sc) * np.abs(V_oc))

        # Saturation: current at most-negative voltage / I_sc
        I_at_V_min = I[0]
        V_min = V[0]
        sat = I_at_V_min / I_sc

        # Dark-dependent outputs
        Id_mpp = nan
        sat_ph = nan

        if has_dark:
            V_dark_lo = V_dark[0]
            V_dark_hi = V_dark[-1]

            # Id_mpp: dark current at V_mpp
            if not np.isnan(V_mpp) and V_dark_lo <= V_mpp <= V_dark_hi:
                Id_mpp = np.interp(V_mpp, V_dark, I_dark)

            # sat_ph: photocurrent saturation at most-negative voltage
            if V_dark_lo <= V_dark_hi:  # check if sweep direction is positive
                I_dark_at_V_min = np.interp(V_min, V_dark, I_dark)
                sat_ph = (I_at_V_min - I_dark_at_V_min) / I_sc

        return [I_sc, V_oc, P_mpp, V_mpp, I_mpp, FF, sat, Id_mpp, sat_ph]


if __name__ == "__main__":

    # Synthetic solar cell model: I = -(I_ph - I_0*(exp(V/(n*Vt)) - 1))
    # Standard SMU sign convention: I_sc < 0, V_oc > 0
    V_light = np.linspace(-0.5, 0.8, 300)
    I_ph = 10e-3    # 10 mA photocurrent
    I_0 = 1e-10     # dark saturation current
    n = 1.5         # ideality factor
    Vt = 0.02585    # thermal voltage at room temperature

    I_light = -(I_ph - I_0 * (np.exp(V_light / (n * Vt)) - 1))

    # Dark curve on a different (coarser) voltage grid
    V_dark = np.linspace(-0.3, 0.7, 60)
    I_dark = I_0 * (np.exp(V_dark / (n * Vt)) - 1)

    script = Main()
    results = script.main(I_light=I_light, V_light=V_light, I_dark=I_dark, V_dark=V_dark)

    print("=== Solar Cell IV Curve Analysis ===")
    for label, unit, val in zip(Main.variables, Main.units, results):
        print(f"  {label}: {val:.4g} {unit}")

    # Expected values
    V_oc_exp = n * Vt * np.log(I_ph / I_0 + 1)
    print(f"\n  Expected I_sc ~ {-I_ph * 1e3:.1f} mA  (= {-I_ph:.4g} A)")
    print(f"  Expected V_oc ~ {V_oc_exp:.4g} V")

    print("\n--- Test: dark curve outside range of V_min (sat_ph should be nan) ---")
    V_dark_narrow = np.linspace(-0.1, 0.7, 30)  # does not cover V_min = -0.5
    I_dark_narrow = I_0 * (np.exp(V_dark_narrow / (n * Vt)) - 1)
    results2 = script.main(
        I_light=I_light, V_light=V_light,
        I_dark=I_dark_narrow, V_dark=V_dark_narrow,
    )
    print(f"  sat_ph: {results2[8]}")  # should be nan
    print(f"  Id_mpp: {results2[7]:.4g} A")  # should be a valid number
