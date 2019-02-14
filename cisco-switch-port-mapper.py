import paramiko
import time
from threading import Thread
import Queue as queue
import csv
import os
import re
import socket
import datetime
import sys
import logging

# Uncomment this line to view SSH debug info
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

username = "username"
password = "password"

# Switch descriptions
# [Switch Number/Name, IP Address, Number of ports]
# Note: Switch Number/Name can also be text
switches = [[1, "192.168.6.130", 28],
            [2, "192.168.6.131", 28],
            [3, "192.168.6.132", 28],
            [4, "192.168.6.133", 28],
            [5, "192.168.6.134", 28]]

# Locations with patch panels and sockets
# [Location Number, Location name]
locations = [[1, "Server Room"],
             [2, "Patch Room - Uplink"],
             [3, "Patch Room - Downlink"],
             [4, "Wall Plug"]]

# Main headers for every file
header = ["Switch", "Port", "Port Name"]

# Determines which location will trigger the request for a description
description_loc = 4

file_name = 'ports_map.csv'

###################################################################


# Trickiness for getting around no authentication on Cisco switches
class patched_SSHClient(paramiko.SSHClient):
    def _auth(self, username, password, *args):
        if not password:
            try:
                self._transport.auth_none(username)
                return
            except paramiko.BadAuthenticationType:
                pass
        paramiko.SSHClient._auth(self, username, password, *args)

###################################################################


# Finds the row in data that matches the switch and port
def find_row(data, sw, port):
    row = 0
    for x in data:
        if x[0] == str(sw) and x[1] == str(port):
            return row
        else:
            row += 1
    return None

###################################################################


# Process that runs for each switch
class SwitchProcessThreader(Thread):
    def __init__(self, switch_id, switch_ip, status_queue):
        Thread.__init__(self)
        self.switch_id = switch_id
        self.switch_ip = switch_ip
        self.status_queue = status_queue
        self.flag = True
        self.stroke_watchdog = False

    def run(self):
        self.status_queue.put({"switch_id": self.switch_id, "status": "connecting... (" + self.switch_ip + ")"})

        client = patched_SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connect to the switch
        try:
            client.connect(self.switch_ip, username=username, allow_agent=False, look_for_keys=False)
        except Exception, err:
            self.status_queue.put({"switch_id": self.switch_id, "status": "error", "err_msg": str(err)})
            client.close()
            return

        self.status_queue.put({"switch_id": self.switch_id, "status": "connected"})

        # Start shell
        remote_conn = client.invoke_shell()
        remote_conn.settimeout(None)
        data = remote_conn.recv(65535)

        # Enter username
        remote_conn.send(username + "\n")
        time.sleep(0.5)
        data = remote_conn.recv(65535)

        # Enter password
        remote_conn.send(password + "\n")
        time.sleep(0.5)
        data = remote_conn.recv(65535)

        # Check for prompt
        if data.find(">") is not -1:
            self.status_queue.put({"switch_id": self.switch_id, "status": "authenticated"})
        else:
            self.status_queue.put({"switch_id": self.switch_id, "status": "NOT authenticated"})
            self.status_queue.put({"switch_id": self.switch_id, "status": "disconnected"})
            client.close()
            return

        remote_conn.settimeout(1)
        all_good = True

        # Continuously wait for data, unless something went wrong
        while all_good and self.flag:

            # Stroke the watchdog
            if self.stroke_watchdog:
                self.stroke_watchdog = False
                try:
                    remote_conn.send("\n")
                except Exception, err:
                    self.status_queue.put({"switch_id": self.switch_id, "status": "error", "err_msg": str(err)})
                    all_good = False
                    continue

            try:
                data = remote_conn.recv(65535)
            except socket.timeout:
                continue
            except Exception, err:
                self.status_queue.put({"switch_id": self.switch_id, "status": "error", "err_msg": str(err)})
                all_good = False
                continue

            # Only report if a link went up or down
            # Extract all the entries containing "%LINK" from the switch
            ranges = [[m.start(), m.end()] for m in re.finditer(r"%LINK.+\n", data)]
            entries = [data[i[0]:i[1]] for i in ranges]

            if len(entries) > 0:
                for x in entries:
                    # Only look at entries that contain "gi" or "fe"
                    if (x.find("gi") is not -1) or (x.find("fe") is not -1):
                        port = x[x.rfind(":") + 1:].strip()
                        if x.find("Up") is not -1:
                            self.status_queue.put({"switch_id": self.switch_id, "status": "port change", "direction": "UP", "port": port})
                        elif x.find("Down") is not -1:
                            self.status_queue.put(
                                {"switch_id": self.switch_id, "status": "port change", "direction": "DOWN", "port": port})

        client.close()
        self.status_queue.put({"switch_id": self.switch_id, "status": "disconnected"}, False, 1)

###################################################################


class WatchdogProcessThreader(Thread):
    def __init__(self, switch_threads):
        Thread.__init__(self)
        self.switch_threads = switch_threads

    def run(self):
        while True:
            time.sleep(60)
            for x in self.switch_threads:
                x.stroke_watchdog = True

###################################################################


def print_with_date(s):
    txt = "[" + datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S') + "] " + s
    print txt

    if False:
        log = "switches log - " + datetime.datetime.today().strftime('%Y %m %d') + ".txt"
        with open(log, "a") as f:
            f.write(txt + "\n")

###################################################################


def raw_input_with_date(s):
    txt = "[" + datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S') + "] " + s
    ret = raw_input(txt)

    return ret

###################################################################


# Main program
def main_program(test_switch):
    status_queue = queue.Queue()

    print "----------------------------"
    print " Welcome to the Port Mapper "
    print "----------------------------"
    print ""
    print "Enter 'ctrl-c' to exit (sometimes works)"
    print ""

    # Populate a blank file if file is missing
    if not os.path.isfile(file_name):
        print "Creating new file: " + file_name
        print ""
        with open(file_name, mode='wb') as writeFile:
            writer = csv.writer(writeFile, delimiter=',')

            full_header = header
            for x in locations:
                full_header.append(x[1])

            full_header.append("Description")

            writer.writerow(full_header)

            for sw in switches:
                for port in range(1, sw[2] + 1):
                    new_row = [sw[0], port, ""]
                    for x in locations:
                        new_row.append("")
                    new_row.append("")  # Extra entry for "Description"
                    writer.writerow(new_row)

    else:
        print "Using existing file: " + file_name
        print ""

    # Display the list of locations
    for x in locations:
        print str(x[0]) + ") " + x[1]

    location = raw_input("Choose a location: ")

    if location.isdigit():
        location = int(location)
        if location < 1 or location > len(locations):
            print "Invalid selection"
            return -1
    else:
        print "Invalid selection"
        return -1

    print "Location '" + locations[location - 1][1] + "' chosen"
    print ""

    # Start a new thread for each switch
    if test_switch is None:
        threads = [SwitchProcessThreader(x[0], x[1], status_queue) for x in switches]
    else:
        threads = [SwitchProcessThreader(switches[test_switch-1][0], switches[test_switch-1][1], status_queue)]

    # Start all threads
    for x in threads:
        x.start()

    # Start watchdog thread
    watchdog_thread = WatchdogProcessThreader(threads)
    watchdog_thread.daemon = True
    watchdog_thread.start()

    try:
        while True:
            # Grab the next entry in the queue
            try:
                s = status_queue.get_nowait()
            except queue.Empty:
                continue

            if s["status"] == "error":
                print_with_date("Switch " + str(s["switch_id"]) + " error: " + s["err_msg"])

            elif s["status"] == "port change":
                # Extract port number from text
                port_num = re.findall(r"\d+", s["port"])[0]

                # Display status
                print_with_date("Switch " + str(s["switch_id"]) + " port " + port_num + " " + s["direction"] + " (" + s[
                    "port"] + ")")

                # Read the entire file into an array
                try:
                    with open(file_name, mode='rb') as readFile:
                        reader = csv.reader(readFile, delimiter=',')
                        lines = list(reader)
                except IOError:
                    print_with_date("     Error opening file")
                    continue

                # Find row with switch and port
                row = find_row(lines, s["switch_id"], port_num)
                if row is None:
                    print_with_date("     Row missing in file")
                    continue

                current_line = lines[row]

                # Get the current entry for that row
                current_value = current_line[location + 2]
                if len(current_value) is 0:
                    current_value = "empty"

                update_necessary = False

                # Request a new entry
                print_with_date("     Current entry for location " + locations[location-1][1] + " is '" + current_value + "'")
                user_input = raw_input_with_date("     Enter new entry or press 'enter' to keep old: ")

                if len(user_input) is 0:
                    print_with_date("     Old value kept")
                else:
                    current_line[location + 2] = user_input
                    current_line[2] = s["port"]
                    lines[row] = current_line
                    update_necessary = True
                    print_with_date("     New value chosen")

                # Display description if at wall plug
                if location == description_loc:
                    # Get the current description for that row
                    current_desc = current_line[len(locations) + 3]
                    if len(current_desc) is 0:
                        current_desc = "empty"

                    # Request a new description
                    print_with_date("     Current description for location " + locations[location - 1][1] + " is '" + current_desc + "'")
                    user_input = raw_input_with_date("     Enter new entry or press 'enter' to keep old: ")

                    if len(user_input) is 0:
                        print_with_date("     Old value kept")
                    else:
                        current_line[len(locations) + 3] = user_input
                        current_line[2] = s["port"]
                        lines[row] = current_line
                        update_necessary = True
                        print_with_date("     New value chosen")

                # Write update to file if necessary
                if update_necessary:
                    success = False
                    while not success:
                        try:
                            with open(file_name, mode='wb') as writeFile:
                                writer = csv.writer(writeFile, delimiter=',')
                                writer.writerows(lines)
                        except IOError:
                            success = False
                            raw_input_with_date("     Error writing to file. Press enter to try again.")
                        else:
                            success = True
                            print_with_date("     New value(s) written to file")

            else:
                print_with_date("Switch " + str(s["switch_id"]) + " " + s["status"])

    except KeyboardInterrupt:
        print_with_date("Program exiting...")

        # Set the exit flag in each thread
        for x in threads:
            x.flag = False

        # Wait for each thread to exit
        for x in threads:
            x.join()

        # Print the final status of each switch
        while not status_queue.empty():
            # Grab the next entry in the queue
            s = status_queue.get_nowait()
            print_with_date("Switch " + str(s["switch_id"]) + " " + s["status"])

###################################################################


res = main_program(test_switch=None)

if res == -1:
    raw_input("\nProgram exited unexpectedly.\nPress enter to exit...")

else:
    raw_input("\nPress enter to exit...")
