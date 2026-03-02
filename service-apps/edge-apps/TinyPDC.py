import time
from synchrophasor.pdc import Pdc
from synchrophasor.frame import DataFrame

"""
tinyPDC will connect to pmu_ip:pmu_port and send request
for header message, configuration and eventually
to start sending measurements.
"""

if __name__ == "__main__":

    pdc = Pdc(pdc_id=7, pmu_ip="pmu-service", pmu_port=1410)
    pdc.logger.setLevel("DEBUG")

    pdc.run() 

    header = pdc.get_header()  
    config = pdc.get_config() 
    
    time_base = 1000000 

    pdc.start()  

    while True:
        data = pdc.get()

        if type(data) == DataFrame:
            arrival_time = time.time()
            print(data.get_measurements())

            raw_soc = data.get_soc()
            raw_fracsec = data.get_frasec() 

            pmu_soc = raw_soc[0] if isinstance(raw_soc, tuple) else raw_soc
            pmu_fracsec = raw_fracsec[0] if isinstance(raw_fracsec, tuple) else raw_fracsec
            
            pmu_timestamp = pmu_soc + (pmu_fracsec / time_base)
            latency = arrival_time - pmu_timestamp
            
            print(f"Latency: {latency * 1000:.4f} ms")

        # if not data:
        #     pdc.quit()
        #     break