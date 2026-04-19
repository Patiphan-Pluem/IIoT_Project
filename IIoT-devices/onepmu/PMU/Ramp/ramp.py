import time
import random
from synchrophasor.frame import ConfigFrame2
from synchrophasor.pmu import Pmu

if __name__ == "__main__":
    pmu = Pmu(ip="0.0.0.0", port=1410)
    pmu.logger.setLevel("INFO")

    cfg = ConfigFrame2(
        1410, 1000000, 1, "Ramp", 1410,
        (True, True, True, True),
        3, 1, 1,
        ["VA","VB","VC","ANALOG1","BREAKER 1 STATUS",
         "BREAKER 2 STATUS","BREAKER 3 STATUS","BREAKER 4 STATUS","BREAKER 5 STATUS",
         "BREAKER 6 STATUS","BREAKER 7 STATUS","BREAKER 8 STATUS","BREAKER 9 STATUS",
         "BREAKER A STATUS","BREAKER B STATUS","BREAKER C STATUS","BREAKER D STATUS",
         "BREAKER E STATUS","BREAKER F STATUS","BREAKER G STATUS"],
        [(0, "v"), (0, "v"), (0, "v")],
        [(1, "pow")],
        [(0x0000, 0xffff)],
        50, 1, 60
    )

    pmu.set_configuration(cfg)
    pmu.set_header("ramp")
    pmu.run()

    start_rate = 25
    end_rate   = 50   

    def precise_sleep_until(target):
        remaining = target - time.time()
        if remaining > 0.002:
            time.sleep(remaining - 0.002)
        while time.time() < target:
            pass

    print("PMU running: ramp", flush=True)

    was_connected = False

    try:
        while True:
            connected = bool(pmu.clients)

            if not connected:
                was_connected = False
                time.sleep(0.2)
                continue

            if not was_connected:
                was_connected = True

            # random hold
            hold_low_sec  = random.uniform(10, 30)   # hold at 20 mps
            ramp_sec      = random.uniform(15, 45)   # ramp 20 to 50
            hold_high_sec = random.uniform(20, 60)   # hold ทat 50 mps

            total = hold_low_sec + ramp_sec + hold_high_sec
            print(f"[PMU] New cycle: hold_low={hold_low_sec:.1f}s  ramp={ramp_sec:.1f}s  hold_high={hold_high_sec:.1f}s  (total={total:.1f}s)", flush=True)

            t0 = time.time()
            next_send = t0

            while pmu.clients:
                t = time.time() - t0

                if t <= hold_low_sec:
                    #hold start_rate
                    rate = start_rate

                elif t <= hold_low_sec + ramp_sec:
                    # ramp
                    t_ramp = t - hold_low_sec
                    rate = start_rate + (end_rate - start_rate) * (t_ramp / ramp_sec)

                elif t <= total:
                    # hold end_rate
                    rate = end_rate

                else:
                    print("[PMU] Cycle complete — restarting", flush=True)
                    break

                pmu.send_data(
                    phasors=[
                        (random.uniform(215.0, 240.0), random.uniform(-0.1, 0.3)),
                        (random.uniform(215.0, 240.0), random.uniform(1.9,  2.2)),
                        (random.uniform(215.0, 240.0), random.uniform(3.0,  3.14)),
                    ],
                    analog=[9.91],
                    digital=[0x0001],
                )

                next_send += 1.0 / rate
                precise_sleep_until(next_send)

    finally:
        pmu.join()