# author: Franz Hempel
# created at: 2026-03-31

import numpy as np


class Main():

    """
    <h2>Transistor Transfer Curve Analysis</h2>
    <p>
    Analyses the transfer curve of a transistor (FET or BJT) measured with three SMUs
    (Drain/Collector, Source/Emitter, Gate/Base). The gate/base voltage is assumed to be
    the sweep axis.
    </p>
    <h3>Outputs</h3>
    <ul>
    <li><b>On/Off ratio</b>: max(|I_D|) / min(|I_D|)</li>
    <li><b>Current gain</b>: I_D / I_G evaluated at the on-state point (argmax |I_D|).
        Returns nan if |I_G| &lt; 1e-15 A (e.g. ideal MOSFET gate).</li>
    <li><b>I_off</b>: Minimum absolute drain/collector current</li>
    <li><b>Transconductance</b>: Peak |dI_D/dV_G| (via numpy gradient)</li>
    <li><b>Threshold voltage</b>: Linear tangent extrapolation to I_D = 0 at the point of
        maximum transconductance. Requires at least 3 data points.</li>
    </ul>
    """

    variables = ["On/Off ratio", "Current gain", "I_off", "Transconductance", "Threshold voltage"]
    units = ["", "", "A", "A/V", "V"]

    arguments = {
        "I_D": (),
        "V_G": (),
        "I_G": (),
        "V_D": (),
        "I_S": (),
        "V_S": (),
    }

    def main(self, **kwargs):

        I_D = np.array(kwargs["I_D"], dtype=float)
        V_G = np.array(kwargs["V_G"], dtype=float)
        I_G = np.array(kwargs["I_G"], dtype=float)

        nan = float("nan")
        nan_result = [nan] * 5

        if len(I_D) < 3:
            return nan_result

        # Sort by V_G ascending
        sort_idx = np.argsort(V_G)
        V_G = V_G[sort_idx]
        I_D = I_D[sort_idx]
        I_G = I_G[sort_idx]

        abs_I_D = np.abs(I_D)

        # Off-current and on/off ratio
        I_off = np.min(abs_I_D)
        I_on = np.max(abs_I_D)
        on_off_ratio = I_on / I_off if I_off > 0 else nan

        # Current gain at on-state point
        idx_on = int(np.argmax(abs_I_D))
        I_G_on = I_G[idx_on]
        current_gain = I_D[idx_on] / I_G_on if np.abs(I_G_on) >= 1e-15 else nan

        # Peak transconductance
        gm = np.gradient(I_D, V_G)
        idx_gm_max = int(np.argmax(np.abs(gm)))
        transconductance = np.abs(gm[idx_gm_max])

        # Threshold voltage: tangent line at max-gm point extrapolated to I_D = 0
        # I_D_tan(V) = I_D[idx] + gm[idx] * (V - V_G[idx])  =>  V_th = V_G[idx] - I_D[idx] / gm[idx]
        gm_at_max = gm[idx_gm_max]
        V_th = V_G[idx_gm_max] - I_D[idx_gm_max] / gm_at_max if gm_at_max != 0 else nan

        return [on_off_ratio, current_gain, I_off, transconductance, V_th]


if __name__ == "__main__":

    # Synthetic NMOS-like transfer curve: sigmoidal I_D(V_G) with known V_th = 1.0 V
    V_G = np.linspace(-2, 4, 200)
    V_th_true = 1.0
    I_D = 1e-3 * (1 + np.tanh(5 * (V_G - V_th_true))) / 2 + 1e-10  # on-current ~1 mA
    I_G = np.full_like(V_G, 1e-12)  # small gate leakage

    script = Main()
    results = script.main(
        I_D=I_D, V_G=V_G, I_G=I_G,
        V_D=np.full_like(V_G, 1.0),
        I_S=-I_D, V_S=np.zeros_like(V_G),
    )

    print("=== Transistor Transfer Curve Analysis ===")
    for label, unit, val in zip(Main.variables, Main.units, results):
        print(f"  {label}: {val:.4g} {unit}")
    print(f"\n  Expected V_th ~ {V_th_true} V")
    print(f"  Expected On/Off ratio ~ {1e-3 / 1e-10:.0e}")
