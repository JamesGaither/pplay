# History #

recently I've been in the need of reproducing some issue with DLP, while I was provided with pcap when DLP was not involved in the traffic flow and everything was working.
Orignally I was trying to utilize netcat, however I've always ended up with some (my) mistake, or simply I just sent CR when it should have been CRLF... Reproduction was frankly tedious task.

Then I gave up on manual work, and tried tcpreplay. This is really fantastic tool in case you want to replay *exactly* what you have in pcap. However I quickly realized that DLP is changing sequential numbers of inspected TCP traffic, so it couldn't have been used it too!! Looking around the net, I decided to write something myself which will help me now and next time it can help others too. That is how pplay was born.

# Quick start #

PPlay is tool to replay/resend application data, it doesn't care of transport layer parameters (which we want, reasons described above). It will grab only the payload from connection you explicitly specify and will make new connection and plays the content in the right order. Of course, you will need to run pplay on server and on client too, with the same pcap file parameter and also with other quite important arguments.

All data about to be sent will be printed out to be confirmed by you. When receiving data, it will tell you if they differ from what we expect and how much; there are 3 levels, OK, modified, different. If they differ significantly (marked as different), they will not be considered as the part of the expected data, so in most cases the logic of packet ordering will stay stable.

Output is colored; RED means anything related to received stuff, GREEN everything to data to be sent, or YELLOW for command line and other data eligible to be sent in the future but not now. WHITE is usually program notifications. At the first sight pplay's output might look bit a messy, but colors really help.


# Replaying PCAP #

#### List connections you have available
```
$ pplay.py --pcap samples/post-chunked-response.pcap --list

10.0.0.20:59471 -> 192.168.132.1:80 (starting at frame 0)
192.168.132.1:80 -> 10.0.0.20:59471 (starting at frame 1)
```

#### Run server side pplay instance 
```
$ ./pplay.py --pcap samples/post-chunked-response.pcap --server 127.0.0.2:9999 --connection 10.0.0.20:59471
```
#### Run client side instance
```
$ ./pplay.py --pcap samples/post-chunked-response.pcap --client 127.0.0.2:9999 --connection 10.0.0.20:59471
```

# Replaying SMCAP (smithproxy captures)


#### Run server pplay instance
```
$ sudo ./pplay.py  --server 127.0.0.2:9999 --smcap samples/smcap_sample.smcap  --ssl
                            listen on this IP:PORT                             optionally wrap it with SSL 
```

#### Run client pplay instance
```
$ ./pplay.py --smcap samples/smcap_sample.smcap --client 127.0.0.2:9999 --ssl
                                                         connect here     optionally wrap payload with SSL
```


# Replaying PPlayScript #
pplay also knows how to export data to a "script". This is extremely convenient to do if you are repeating the same test again and again, needing to change parts of the payload dynamically. Output script is in fact a python class, containing also all necessary data, no --pcap or --smcap arguments are needed anymore.

You can produce script with --export <scriptname> (filename will be scriptname.py). You can then use it by --script scriptname (instead of --pcap or --smcap arguments).
For example:

```
$ ./pplay.py --pcap samples/post-chunked-response.pcap  --connection 10.0.0.20:59471 --export stuff

Template python script has been exported to file stuff.py
```

#### You can use "script" as the sniff file (NOTE: missing .py in --script argument)
```
$ ./pplay.py --script stuff --server 127.0.0.2:9999
$ ./pplay.py --script stuff --client 127.0.0.2:9999 
```


Main purpose of it is the need of dynamic modification of the payload, or other "smart" stuff, that cannot be predicted and programmed for you in pplay directly.

#### Simplistic script example:


```
#!python

import datetime

class PPlayScript:

    def __init__(self,pplay):
	    # access to pplay engine
	    self.pplay = pplay

	    self.packets = []
	    self.packets.append('C1\r\n')
	    self.packets.append('S1\r\n')
	    self.packets.append('C2\r\n')
	    self.packets.append('S2\r\n')

	    self.origins = {}

	    self.server_port = 80
	    self.origins['client']=[0,2]
	    self.origins['server']=[1,3]



    def before_send(self,role,index,data):
	    # when None returned, no changes will be applied and packets[ origins[role][index] ] will be used
	    if role == 'server' and index == 1:
		    return data + ": %s"  % (datetime.datetime.now(),)

	    return None

    def after_received(self,role,index,data):
	    # return value is ignored: use it as data gathering for further processing
	    return None

```

As you might see this gives to your hands power to export existing payload with --export and modify it on the fly as you want. You can make a string templates from it and just paste values as desired, or you can write even quite complex code around!




# More details #
PPlay forgets everything about original IP addresses. It's because you will be testing it in your lab testbed. Only thing it will remember is the the destination port, for server side pplay it's important, meaning the port where it should *listen* for incoming connections. But that's really it.

Client-side pplay will connect to the server-side. Once connected, you will see on one side green hex data and on the other yellow hex data. For HTTP, the client-side would be typically green, since HTTP comes with the request first. On the line above green hex data you will also see e.g. "[1/2] (in sync) offer to send -->". In sync is important here. Those data should be sent now according to pcap.
If you see yellow data, that side is not on it's turn, and you will not see also "(in sync)" above them.

Yellow or green, pplay will act on behalf of you by default in 5 seconds => green data will be sent.
Hint: you can set --noauto, or --auto <big_seconds> program argument to change autosend feature. This feature could be also toggled on/off during the operation with "i" command shortcut.


## Commands ##
Below hex data (green or yellow), there is some contextual help for you: pplay is waiting for your override action to it's default -- autosend. At the time being, you can enter:

    "y" or hit <enter> to send data
    "s" to skip them
    "c" to send CR only
    "l" to send LF only
    "x" to send CR+LF characters
    "i" to disable/enable autosend feature
    "r" command to replace content of the payload with something else. 
        It does have 'vi'-like syntax: r/POST/GET/0 will replace string "POST" with "GET". 
        Trailing number means max. number of replacements, 0=all

## Data sources ##
PPlay also supports smithproxy output, just use --smcap instead of --pcap argument option.
You can wrap the traffic into SSL, just use --ssl option. With smithproxy together, pplay is quite powerful pair of tools: you can easily replay "decrypted" smcap file from smithproxy and wrap it again into SSL to further test.

Hint: Smithproxy it's SSL mitm proxy written by me in C/C++, faking certificate subject. It utilizes iptables TPROXY target. SSL traffic is signed by local CA and plaintext is logged into files.

# Requirements #
Tool doesn't have too requirements. You have to have installed scapy and colorama python packages.

Scapy is used to parse pcaps and to have scapy available for future features - runs on Linux, Mac and Windows (see instructions how to install scapy on windows here). It's known to not work in Cygwin.

Note: I am deciding to drop scapy in the future.
Colorama is responsible for multiplatform coloring. On windows, unpack zip-file, run cmd and run python setup.py install. That should make it.

I would recommend to run pplay in linux, I haven't tested it on Windows yet.




# SMCAP2PCAP tool
This tool is a bit hack. Basically it replays smcap file, while using tcpdump to sniff the traffic. There are dozens of reasons why you would like to convert smcap file to pcap. This is the tool for that purpose.

Also, this tools is very basic. There is only argument it takes: smcap file. Name and location of the converted pcap will be printed out.