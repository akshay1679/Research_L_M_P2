# analysis/trajectory.py
# Software-emulated Trajectory Analysis (TA)

def trajectory_analysis(link_delays, switch_delays):
    """
    link_delays: list of link delays
    switch_delays: list of switch delays
    """

    total_delay = 0
    for ld in link_delays:
        total_delay += ld

    for sd in switch_delays:
        total_delay += sd

    return total_delay
