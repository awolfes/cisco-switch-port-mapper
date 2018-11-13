# cisco-switch-port-mapper
Python script to help map a network connected to Cisco switches.

Every time a cable is connected to (or disconnected from) a supported Cisco switch, a message is displayed over SSH, similar to the following:

    Switch8>12-Nov-2018 17:34:20 %LINK-W-Down:  gi20
    12-Nov-2018 17:34:25 %LINK-I-Up:  gi20

This script aggregates these messages from multiple switches. By unplugging and plugging in devices at each network hop, a map of the network can slowly be formed. This is useful in situations where the network ports and patch panels have not been proplerly labeled. When first started, the script will create a CSV file (if it doesn't already exist) with all the necessary information. It will then ask the user where they are, ie. what hop of the network they are at. The user then needs to connect and disconnect each network cable and tell the script the name of the plug.

    Switch 8 port 20 DOWN (gi20)
         Current entry for location Patch Room - Uplink is 'empty'
         Enter new entry or press 'enter' to keep old: A17
         New value chosen
         New value(s) written to file
    Switch 8 port 20 UP (gi20)
         Current entry for location Patch Room - Uplink is 'A17'
         Enter new entry or press 'enter' to keep old: 
         Old value kept

Each entry is checked against the current entry in the CSV file, and the new entry is saved. If the location is at the "Wall Plug" then an additional description can be added.

    Switch 8 port 20 DOWN (gi20)
         Current entry for location Wall Plug is 'empty'
         Enter new entry or press 'enter' to keep old: Q123
         New value chosen
         Current description for location Wall Plug is 'empty'
         Enter new entry or press 'enter' to keep old: Computer
         New value chosen
         New value(s) written to file
    Switch 8 port 20 UP (gi20)
         Current entry for location Wall Plug is 'Q123'
         Enter new entry or press 'enter' to keep old: 
         Old value kept
         Current description for location Wall Plug is 'Computer'
         Enter new entry or press 'enter' to keep old: 
         Old value kept
         
## Requirements
- Python 2.7
- Paramiko for SSH (http://www.paramiko.org/)
- Tested and designed to work with SG300-28P switches from Cisco.
- The Syslog Aggregator should be disabled in each switch so that the messages will appear immediately. (https://community.cisco.com/t5/small-business-support-documents/configure-log-aggregation-settings-on-an-sx350-series-managed/ta-p/3170437)

## Instructions
Variables at the top of the file:

    username = "username"
    password = "password"
    
    switches = [[1, "192.168.6.130", 28],
                [2, "192.168.6.131", 28],
                [3, "192.168.6.132", 28],
                [4, "192.168.6.133", 28],
                [5, "192.168.6.134", 28]]
                
    locations = [[1, "Server Room"],
                 [2, "Patch Room - Uplink"],
                 [3, "Patch Room - Downlink"],
                 [4, "Wall Plug"]]
             
    header = ["Switch", "Port", "Port Name"]
    
    description_loc = 4

    file_name = 'ports_map.csv'

username - Log in name for the switch.

password - Log in password for the switch.

switches - The list of switches, formatted: [Switch Number/Name, IP Address, Number of ports]. Note: Switch Number/Name can also be text.

locations - Locations with patch panels and sockets, formatted: [Location Number, Location name].

header - Main header that appears at the top of every file, including the Switch Name, Port Number, and Port Name.

description_loc - Determines which location will trigger the request for a description. By default it's the Wall Plug.

file_name - The name of the file that will be generated and then used.

For debugging purposes, the line at the top of the script that calls logging.basicConfig can be uncommented to view SSH debug info:

    # Uncomment this line to view SSH debug info
    #logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    
Additionally, the main program can be run with just one switch to troubleshoot any connection issues:

    res = main_program(test_switch=3)
