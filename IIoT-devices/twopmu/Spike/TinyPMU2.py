import time
import random
from synchrophasor.frame import ConfigFrame2
from synchrophasor.pmu import Pmu

# config
PQM_PORT      = 1411
SPIKE_RATE    = 50      
LAMBDA_ARRIVE = 0.05    # mean inter-spike 20 s 
SPIKE_DUR_MIN = 1.0  
SPIKE_DUR_MAX = 3.0    


BUSYWAIT_THRESHOLD = 0.002

def precise_sleep_until(target):
    remaining = target - time.time()
    if remaining > BUSYWAIT_THRESHOLD:
        time.sleep(remaining - BUSYWAIT_THRESHOLD)
    while time.time() < target:
        pass

if __name__ == "__main__":
    pqm = Pmu(ip="0.0.0.0", port=PQM_PORT)
    pqm.logger.setLevel("INFO")

    cfg = ConfigFrame2(
        PQM_PORT, 1000000, 1, "PQM Station", PQM_PORT,
        (True, True, True, True),
        3, 1, 1,
        ["VA","VB","VC","ANALOG1","BREAKER 1 STATUS",
         "BREAKER 2 STATUS","BREAKER 3 STATUS","BREAKER 4 STATUS","BREAKER 5 STATUS",
         "BREAKER 6 STATUS","BREAKER 7 STATUS","BREAKER 8 STATUS","BREAKER 9 STATUS",
         "BREAKER A STATUS","BREAKER B STATUS","BREAKER C STATUS","BREAKER D STATUS",
         "BREAKER E STATUS","BREAKER F STATUS","BREAKER G STATUS"],
        [(0,"v"),(0,"v"),(0,"v")],
        [(1, "pow")],
        [(0x0000, 0xffff)],
        50, 1, SPIKE_RATE
    )

    pqm.set_configuration(cfg)
    pqm.set_header("spike-PQM")
    pqm.run()

    print(f"PQM spike running | port={PQM_PORT} | spike_rate={SPIKE_RATE}fps | λ={LAMBDA_ARRIVE}", flush=True)

    try:
        while True:
            if not pqm.clients:
                time.sleep(0.1)
                continue

            #inter-spike interval Poisson
            wait = random.expovariate(LAMBDA_ARRIVE)
            print(f"[PQM] Quiet for {wait:.1f}s...", flush=True)
            time.sleep(wait)

            if not pqm.clients:
                continue

            # spike burst
            spike_dur = random.uniform(SPIKE_DUR_MIN, SPIKE_DUR_MAX)
            print(f"[PQM] >>> SPIKE {spike_dur:.1f}s at {SPIKE_RATE}fps", flush=True)

            spike_end = time.time() + spike_dur
            next_time = time.time()
            dt = 1.0 / SPIKE_RATE

            while time.time() < spike_end and pqm.clients:
                pqm.send_data(
                    phasors=[
                        (random.uniform(215.0, 240.0), random.uniform(-0.1, 0.3)),
                        (random.uniform(215.0, 240.0), random.uniform(1.9,  2.2)),
                        (random.uniform(215.0, 240.0), random.uniform(3.0,  3.14)),
                    ],
                    analog=[9.91],
                    digital=[0x0001],
                )
                next_time += dt
                precise_sleep_until(next_time)

            print(f"[PQM] Spike ended", flush=True)

    finally:
        pqm.join()