from synchrophasor.pmu import Pmu
from synchrophasor.frame import ConfigFrame2
import time
import random

if __name__ == "__main__":
    pmu = Pmu(ip="0.0.0.0", port=1410)
    pmu.logger.setLevel("DEBUG")

    cfg = ConfigFrame2(1410, 1000000, 1, "Random Station", 1410, (True, True, True, True), 
                       3, 1, 1, 
                       ["VA", "VB", "VC", "ANALOG1", "BREAKER 1 STATUS",
                        "BREAKER 2 STATUS", "BREAKER 3 STATUS", "BREAKER 4 STATUS", "BREAKER 5 STATUS",
                        "BREAKER 6 STATUS", "BREAKER 7 STATUS", "BREAKER 8 STATUS", "BREAKER 9 STATUS",
                        "BREAKER A STATUS", "BREAKER B STATUS", "BREAKER C STATUS", "BREAKER D STATUS",
                        "BREAKER E STATUS", "BREAKER F STATUS", "BREAKER G STATUS"], 
                       [(0, "v"), (0, "v"), (0, "v")], 
                       [(1, "pow")], [(0x0000, 0xffff)], 50, 1, 30)
    
    pmu.set_configuration(cfg)
    pmu.set_header("Hello! I'm TinyPMU")
    
    pmu.run() 
    print("PMU Server Started on port 1410")


    SLEEP_TIME = 1.0 / 30 

    while True:
        if pmu.clients: 
            pmu.send_data(phasors=[(random.uniform(215.0, 240.0), random.uniform(-0.1, 0.3)),
                                   (random.uniform(215.0, 240.0), random.uniform(1.9, 2.2)),
                                   (random.uniform(215.0, 240.0), random.uniform(3.0, 3.14))],
                          analog=[9.91],
                          digital=[0x0001])
            
        time.sleep(SLEEP_TIME)

    pmu.join()