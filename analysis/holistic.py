# analysis/holistic.py
# Paper-faithful Holistic Analysis (Eq. 6–8)

import math

def holistic_analysis(flow, interfering_flows):
    """
    flow: dict {Ci, Ti, Di, Ji}
    interfering_flows: list of dicts [{Cj, Tj, Jj}]
    """

    Ci = flow['Ci']
    Ti = flow['Ti']
    Di = flow['Di']
    Ji = flow.get('Ji', 0)

    # -------------------------------
    # Eq. (6) – Busy period w
    # -------------------------------
    w = Ci
    while True:
        interference = 0
        for f in interfering_flows:
            interference += math.ceil((w + f['Jj']) / f['Tj']) * f['Cj']

        w_new = Ci + interference
        if w_new == w:
            break
        w = w_new

        if w > 10 * Di:  # safety bound
            return None

    # -------------------------------
    # Eq. (7) + Eq. (8)
    # -------------------------------
    Q = math.ceil((w + Ji) / Ti)
    R_max = 0

    for q in range(Q):
        v = q * Ci
        while True:
            interference = 0
            for f in interfering_flows:
                interference += math.ceil((v + f['Jj']) / f['Tj']) * f['Cj']

            v_new = q * Ci + interference
            if v_new == v:
                break
            v = v_new

        Rq = v + Ci - q * Ti
        R_max = max(R_max, Rq)

    return R_max
