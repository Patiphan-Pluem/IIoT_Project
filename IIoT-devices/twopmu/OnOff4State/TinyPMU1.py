import time
import random
from synchrophasor.frame import ConfigFrame2
from synchrophasor.pmu import Pmu

if __name__ == "__main__":

    pmu = Pmu(ip="0.0.0.0", port=1410)
    pmu.logger.setLevel("INFO")

    freq      = 50
    rate_on   = 50   
    rate_off  = 10    

    cfg = ConfigFrame2(
        1410, 1000000, 1, "On-Off UTC Station", 1410,
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
        freq, 1, rate_on
    )

    pmu.set_configuration(cfg)
    pmu.set_header("On-Off-PMU")
    pmu.run()

    lambda_on  = 1/90
    lambda_off = 1/90

    current_state     = "ON"
    state_expiry_time = time.time() + random.expovariate(lambda_on)
    streaming_started = False
    next_time         = 0

    print(f"PMU running: ON={rate_on}fps OFF={rate_off}fps", flush=True)

    def precise_sleep_until(target):
        remaining = target - time.time()
        if remaining > 0.002:
            time.sleep(remaining - 0.002)
        while time.time() < target:
            pass

    try:
        while True:
            now = time.time()

            # State transition
            if now >= state_expiry_time:
                if current_state == "ON":
                    current_state = "OFF"
                    duration = random.expovariate(lambda_off)
                    state_expiry_time = now + duration
                    streaming_started = False
                    print(f"[{time.strftime('%H:%M:%S')}] >>> Switch to OFF ({duration:.1f}s)", flush=True)
                else:
                    current_state = "ON"
                    duration = random.expovariate(lambda_on)
                    state_expiry_time = now + duration
                    streaming_started = False
                    print(f"[{time.strftime('%H:%M:%S')}] >>> Switch to ON ({duration:.1f}s)", flush=True)

            connected = bool(pmu.clients)

            if not connected:
                streaming_started = False
                time.sleep(0.01)
                continue

       
            current_rate = rate_on if current_state == "ON" else rate_off
            dt = 1.0 / current_rate

            
            if not streaming_started:
                print(f"[PMU] Aligning with UTC rollover... (state={current_state})", flush=True)
                next_time = time.time() // 1 + 1
                remaining = next_time - time.time()
                if remaining > 0.002:
                    time.sleep(remaining - 0.002)
                while time.time() < next_time:
                    pass
                streaming_started = True
                print(f"[PMU] Start streaming at {time.strftime('%H:%M:%S')} | {current_rate}fps", flush=True)

            pmu.send_data(
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

    finally:
        pmu.join()