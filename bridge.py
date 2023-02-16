### This is a minimal version of the Kobold Horde bridge intended for Unattended use ###
### Please use it responsibly! ###

### - Concedo - ###

import requests, json, time, argparse, urllib3
import random

def locallog(obj):
    #print(obj) # comment to run in full stealth mode and do not output anything at all
    pass

class temp(object):
    def __init__(self):
        random.seed()
        self.cluster_url = "http://koboldai.net"    # The cluster url       
        self.kai_url = "http://localhost:5000"      # Where can your bridge reach your KAI instance       
        self.kai_name = f"KG Auto Instance #{random.randint(-100000000, 100000000)}"  # Keep it random
        self.api_key = "0000000000"                 # The api_key identifies a unique user in the horde. For unattended use, we use the anon key
        self.priority_usernames = []

cd = temp()

class kai_bridge():
    def __init__(self):
        self.model = ''
        self.max_content_length = 1024
        self.max_length = 80
        self.current_softprompt = None
        self.softprompts = {}
        self.run = True

        #reduce and vary polling intervals to be less obvious
        self.stealth_interval_min = 9
        self.stealth_interval_max = 12
        self.awake_interval_min = 2.5
        self.awake_interval_max = 3.5
        self.cycles_before_stealth = 15
        self.cycles_before_stealth_counter = 0
            
    def stop(self):
        self.run = False
    
    def validate_kai(self, kai):
        try:
            req = requests.get(kai + '/api/latest/model')
            self.model = req.json()["result"]
            req = requests.get(kai + '/api/latest/config/max_context_length')
            self.max_content_length = req.json()["value"]
            req = requests.get(kai + '/api/latest/config/max_length')
            self.max_length = req.json()["value"]
            if self.model not in self.softprompts:
                    req = requests.get(kai + '/api/latest/config/soft_prompts_list')
                    self.softprompts[self.model] = [sp['value'] for sp in req.json()["values"]]
            req = requests.get(kai + '/api/latest/config/soft_prompt')
            self.current_softprompt = req.json()["value"]
        except requests.exceptions.JSONDecodeError:
            locallog(f"Server {kai} is up but does not appear to be a KoboldAI server. Are you sure it's running the UNITED branch?")
            return(False)
        except requests.exceptions.ConnectionError:
            locallog(f"Server {kai} is not reachable. Are you sure it's running?")
            return(False)
        return(True)


    def bridge(self, api_key, kai_name, kai_url, cluster, priority_usernames):
        current_id = None
        current_payload = None
        return_error = None
        loop_retry = 0
        failed_requests_in_a_row = 0
        interval = 100

        while self.run:

            self.cycles_before_stealth_counter += 1
            if self.cycles_before_stealth_counter > self.cycles_before_stealth:
                interval = random.uniform(self.stealth_interval_min, self.stealth_interval_max)
            else:
                interval = random.uniform(self.awake_interval_min, self.awake_interval_max)

            if loop_retry > 3 and current_id:
                locallog(f"Exceeded retry count {loop_retry} for generation id {current_id}. Aborting generation!")
                current_id = None
                current_payload = None
                current_generation = None
                return_error = None
                loop_retry = 0
                failed_requests_in_a_row += 1
                if failed_requests_in_a_row > 3:
                    locallog(f"{failed_requests_in_a_row} Requests failed in a row. Crashing bridge!")
                    return
            elif current_id:
                locallog(f"Retrying ({loop_retry}/10) for generation id {current_id}...")
            if not self.validate_kai(kai_url):
                locallog(f"Waiting 10 seconds...")
                time.sleep(10)
                continue
            headers = {"apikey": api_key}
            gen_dict = {
                "name": kai_name,
                "model": self.model,
                "max_length": self.max_length,
                "max_content_length": self.max_content_length,
                "priority_usernames": priority_usernames,
                "softprompts": self.softprompts[self.model],
            }
            if current_id:
                loop_retry += 1
            else:
                try:
                    pop_req = requests.post(cluster + '/api/v2/generate/pop', json = gen_dict, headers = headers)
                except (urllib3.exceptions.MaxRetryError, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
                    locallog(f"Server {cluster} unavailable during pop. Waiting 10 seconds...")
                    time.sleep(10)
                    continue
                except requests.exceptions.JSONDecodeError():
                    locallog(f"Server {cluster} unavailable during pop. Waiting 10 seconds...")
                    time.sleep(10)
                    continue
                if not pop_req.ok:
                    locallog(f"During gen pop, server {cluster} responded: {pop_req.text}. Waiting for 10 seconds...")
                    time.sleep(10)
                    continue
                pop = pop_req.json()
                if not pop:
                    locallog(f"Something has gone wrong with {cluster}. Please inform its administrator!")
                    time.sleep(interval)
                    continue
                if not pop["id"]:
                    locallog(f"Server {cluster} has no valid generations to do for us. Skipped Info: {pop['skipped']}.")
                    time.sleep(interval)
                    continue
                current_id = pop['id']
                current_payload = pop['payload']
                if 'width' in current_payload or 'length' in current_payload or 'steps' in current_payload:
                    locallog(f"Stable Horde payload detected: {current_payload}. Aborting ")
                    current_id = None
                    current_payload = None
                    current_generation = None
                    return_error = None
                    loop_retry = 0
                    continue
                # By default, we don't want to be annoucing the prompt send from the Horde to the terminal
                current_payload['quiet'] = True
                requested_softprompt = pop['softprompt']
            if requested_softprompt != self.current_softprompt:
                req = requests.put(kai_url + '/api/latest/config/soft_prompt/', json = {"value": requested_softprompt})
                time.sleep(1) # Wait a second to unload the softprompt
            try:
                gen_req = requests.post(kai_url + '/api/latest/generate/', json = current_payload)
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
                locallog(f"Worker {kai_url} unavailable. Waiting 10 seconds...")
                loop_retry += 1
                time.sleep(10)
                continue
            if type(gen_req.json()) is not dict:
                locallog(f'KAI instance {kai_url} API unexpected response on generate: {gen_req}. Sleeping 10 seconds...')
                time.sleep(9)
                loop_retry += 1
                continue
            if gen_req.status_code == 503:
                locallog(f'KAI instance {kai_url} Busy (attempt {loop_retry}). Will try again...')
                loop_retry += 1
                continue
            if gen_req.status_code == 422:
                locallog(f'KAI instance {kai_url} reported validation error. Returning as error.')
                return_error = "payload validation error"
            if return_error:
                submit_dict = {
                    "id": current_id,
                    "generation": return_error,
                }
            else:
                try:
                    req_json = gen_req.json()
                except json.decoder.JSONDecodeError:
                    locallog(f"Something went wrong when trying to generate on {kai_url}. Please check the health of the KAI worker. Retrying 10 seconds...")
                    loop_retry += 1
                    time.sleep(interval)
                    continue
                try:
                    current_generation = req_json["results"][0]["text"]
                except KeyError:
                    locallog(f"Unexpected response received from {kai_url}: {req_json}. Please check the health of the KAI worker. Retrying in 10 seconds...")
                    locallog(current_payload)
                    loop_retry += 1
                    time.sleep(interval)
                    continue
                submit_dict = {
                    "id": current_id,
                    "generation": current_generation,
                }
            while current_id and current_generation:
                try:
                    submit_req = requests.post(cluster + '/api/v2/generate/submit', json = submit_dict, headers = headers)
                    if submit_req.status_code == 404:
                        locallog(f"The generation we were working on got stale. Aborting!")
                    elif not submit_req.ok:
                        if "already submitted" in submit_req.text:
                            locallog(f'Server think this gen already submitted. Continuing')
                        else:
                            locallog(submit_req.status_code)
                            locallog(f"During gen submit, server {cluster} responded: {submit_req.text}. Waiting for 10 seconds...")
                            loop_retry += 1
                            time.sleep(10)
                            continue
                    else:
                        locallog(f'Submitted generation with id {current_id} and contributed for {submit_req.json()["reward"]}')
                        failed_requests_in_a_row = 0
                        self.cycles_before_stealth_counter = 0
                        interval = random.uniform(self.awake_interval_min, self.awake_interval_max)

                    current_id = None
                    current_payload = None
                    current_generation = None
                    return_error = None
                    loop_retry = 0
                except (urllib3.exceptions.MaxRetryError, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
                    locallog(f"Server {cluster} unavailable during submit. Waiting 10 seconds...")
                    loop_retry += 1
                    time.sleep(10)
                    continue
            time.sleep(interval)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-a', '--api_key', action="store", required=False, type=str, help="The API key corresponding to the owner of the KAI instance")
    arg_parser.add_argument('-n', '--kai_name', action="store", required=False, type=str, help="The server name. It will be shown to the world and there can be only one.")
    arg_parser.add_argument('-k', '--kai_url', action="store", required=False, type=str, help="The KoboldAI server URL. Where the bridge will get its generations from.")
    arg_parser.add_argument('-c', '--cluster_url', action="store", required=False, type=str, help="The KoboldAI Cluster URL. Where the bridge will pickup prompts and send the finished generations.")
    arg_parser.add_argument('--debug', action="store_true", default=False, help="Show debugging messages.")
    arg_parser.add_argument('--priority_usernames',type=str, action='append', required=False, help="Usernames which get priority use in this server. The owner's username is always in this list.")
    arg_parser.add_argument('-v', '--verbosity', action='count', default=0, help="The default logging level is ERROR or higher. This value increases the amount of logging seen in your screen")
    arg_parser.add_argument('-q', '--quiet', action='count', default=0, help="The default logging level is ERROR or higher. This value decreases the amount of logging seen in your screen")
    args = arg_parser.parse_args()
    
    api_key = args.api_key if args.api_key else cd.api_key
    kai_name = args.kai_name if args.kai_name else cd.kai_name
    kai_url = args.kai_url if args.kai_url else cd.kai_url
    cluster = args.cluster_url if args.cluster_url else cd.cluster_url
    priority_usernames = args.priority_usernames if args.priority_usernames else cd.priority_usernames
    locallog(f"{kai_name} Instance Started")
    try:
        kai_bridge().bridge(api_key, kai_name, kai_url, cluster, priority_usernames)
    except KeyboardInterrupt:
        locallog(f"Keyboard Interrupt Received. Ending Process")
    locallog(f"{kai_name} Instance Stopped")
