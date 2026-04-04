import time
import random
from synchrophasor.frame import ConfigFrame2
from synchrophasor.pmu import Pmu


if __name__ == "__main__":
    
    pmu = Pmu(ip="0.0.0.0", port=1410)
    pmu.logger.setLevel("DEBUG")

    freq = 50
    base_rate = 25 # for50 Hz base rate is 10,25,50 message/sec
                   # for 60 Hz base rate is 10,12,15,20,30,60 message/sec

    cfg = ConfigFrame2(
        1410, 1000000, 1, "Baseline Station", 1410,
        (True, True, True, True),
        3, 1, 1,
        ["VA","VB","VC","ANALOG1","BREAKER 1 STATUS",
         "BREAKER 2 STATUS","BREAKER 3 STATUS","BREAKER 4 STATUS","BREAKER 5 STATUS",
         "BREAKER 6 STATUS","BREAKER 7 STATUS","BREAKER 8 STATUS","BREAKER 9 STATUS",
         "BREAKER A STATUS","BREAKER B STATUS","BREAKER C STATUS","BREAKER D STATUS",
         "BREAKER E STATUS","BREAKER F STATUS","BREAKER G STATUS"],
        [(0,"v"),(0,"v"),(0,"v")],
        [(1,"pow")],
        [(0x0000,0xffff)],
        freq, 1, base_rate
    )

    pmu.set_configuration(cfg)
    pmu.set_header("baseline-PMU")
    pmu.run()
    print("PMU running: baseline")

    dt = 1.0 / base_rate

    streaming_started = False

    try:
        while True:
            connected = bool(pmu.clients) #pdc connection

            # don't sent message
            if not connected:
                streaming_started = False
                time.sleep(0.2)
                continue

            # sent message
            if not streaming_started:
    
                print("[PMU] client connected. Aligning with UTC rollover...")
                # UTC second rollover
                next_time = time.time() // 1 + 1
                while time.time() < next_time:
                    pass 
                
                streaming_started = True
                print("[PMU] start streaming")

        
            pmu.send_data(
                phasors=[
                    (random.uniform(215.0, 240.0), random.uniform(-0.1, 0.3)),
                    (random.uniform(215.0, 240.0), random.uniform(1.9, 2.2)),
                    (random.uniform(215.0, 240.0), random.uniform(3.0, 3.14)),
                ],
                analog=[9.91],
                digital=[0x0001],
            )
            
            # Evenly Spaced
            # spacing for each frame 1/N s
            next_time += dt
            
            # Busy Wait
            while time.time() < next_time:
                pass

    finally:
        pmu.join()