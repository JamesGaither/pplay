#!/usr/bin/env python

from __future__ import print_function

import sys
import os
import time
import socket
import time
import difflib
import re
import argparse
import fileinput
import binascii
import datetime
import pprint

from scapy.all import *
#from select import select

have_colorama = False
have_ssl = False

option_dump_received_correct = False;
option_dump_received_different = True;
option_auto_send = 5


pplay_version = "1.1"

title='pplay - application payload player - %s' % (pplay_version,)
copyright="written by Ales Stibal <astibal@gmail.com> (c) 2014"


g_script_module = None

try:
    import colorama
    from colorama import Fore, Back, Style
    
    have_colorama = True
except ImportError, e:
    print('No colorama, enjoy.')
    

try:
    import ssl
    have_ssl = True
except ImportError, e:
    print('No SSL support!')


def str_time():
    t = datetime.datetime.now()
    return str(t)

def print_green_bright(what):
    if have_colorama:
        print(Fore.GREEN + Style.BRIGHT + what)
    else:
        print(what)

def print_green(what):
    if have_colorama:
        print(Fore.GREEN + what)
    else:
        print(what)


def print_yellow_bright(what):
    if have_colorama:
        print(Fore.YELLOW + Style.BRIGHT + what)
    else:
        print(what)

def print_yellow(what):
    if have_colorama:
        print(Fore.YELLOW + what)
    else:
        print(what)

def print_red_bright(what):
    if have_colorama:
        print(Fore.RED + Style.BRIGHT + what)
    else:
        print(what)

def print_red(what):
    if have_colorama:
        print(Fore.RED + what)
    else:
        print(what)

def print_white_bright(what):
    if have_colorama:
        print(Fore.WHITE + Style.BRIGHT + what)
    else:
        print(what)

def print_white(what):
    if have_colorama:
        print(Fore.WHITE + what)
    else:
        print(what)



__vis_filter = """................................ !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[.]^_`abcdefghijklmnopqrstuvwxyz{|}~................................................................................................................................."""

def hexdump(buf, length=16):
    """Return a hexdump output string of the given buffer."""
    n = 0
    res = []
    while buf:
        line, buf = buf[:length], buf[length:]
        hexa = ' '.join(['%02x' % ord(x) for x in line])
        line = line.translate(__vis_filter)
        res.append('  %04d:  %-*s %s' % (n, length * 3, hexa, line))
        n += length
    return '\n'.join(res)

import re

def colorize(s,keywords):
    t = s
    for k in keywords:
        t = re.sub(k, Fore.CYAN+Style.BRIGHT+k+Fore.RESET+Style.RESET_ALL,t)
        
    return t

#print_green_bright("TEST%d:%s" % (12,54))

class Repeater:

    def __init__(self,fnm,server_ip):
        
        self.fnm = fnm
        
        self.packets = []
        self.origins = {}
        
        # write this data :)
        self.to_send = ''
        
        # list of indexes in packets
        self.origins['client'] = []
        self.origins['server'] = []
        
        self.server_port = 0
        self.server_replaced_ip = server_ip
        
        self.whoami = ""
        
        # index of our origin
        self.packet_index = 0
        
        # index of in all packets regardless of origin
        self.total_packet_index = 0
        
        
        self.use_ssl = False

        self.tstamp_last_read = 0
        self.tstamp_last_write = 0
        self._last_countdown_print = 0

        self.scripter = None


    def load_scripter_defaults(self):
        if self.scripter:
            self.server_port = self.scripter.server_port
            self.packets = self.scripter.packets
            self.origins = self.scripter.origins

    def list_pcap(self):
        
        flows = {}
        frame = -1
        
        s = rdpcap(self.fnm)
        for i in s:
            
            frame+=1
            
            sip = i[IP].src
            dip = i[IP].dst
            sport = str(i[TCP].sport)
            dport = str(i[TCP].dport)

            key = sip+":"+sport+" -> "+dip+":"+dport
            if key not in flows:
                print_yellow("%s (starting at frame %d)" % (key,frame))
                flows[key] = "yes"


    def read_pcap(self,im_ip, im_port):

        s = rdpcap(self.fnm)

        #print("Looking for client connection %s:%s" % (im_ip,im_port))

        for i in s:
            sip = i[IP].src
            dip = i[IP].dst
            sport = str(i[TCP].sport)
            dport = str(i[TCP].dport)

            #print ">>> %s:%s -> %s:%s" % (sip,sport,dip,dport)


            origin = None

            if sip == im_ip and sport == im_port:
                origin = "client"
                if self.server_port == 0: 
                   self.server_port = dport                
                
            elif dip == im_ip and dport == im_port:
                origin = "server"
                
        
            if origin:
                p = i[TCP].payload
                if len(p) == 0:
                    #print "No payload"
                    continue
                
                current_index = len(self.packets)
                
                self.packets.append(p)
                self.origins[origin].append(current_index)
               
                #print "%s payload:\n>>%s<<" % (origin,p,)


    def read_smcap(self, im_ip, im_port):
        file_packets = []

        self.packets = []
        self.origins["client"] = []
        self.origins["server"] = []
        
        this_packet_origin = None
        this_packet_index = 0
        this_packet_bytes = []

        have_connection = False
        
        for line in fileinput.input(files=[self.fnm,]):
            #print_yellow("Processing: " + line.strip())
            
            re_packet_start = re.compile(r'^\+\d+: +\d+::([^:]+):([^:]+)-\d+::([^:]+):([^:(]+)')
            re_packet_content_client = re.compile(r'^>\[([0-9a-f])+\][^0-9A-F]+([0-9A-F ]{2,49})')
            re_packet_content_server = re.compile(r'^ +<\[([0-9a-f])+\][^0-9A-F]+([0-9A-F ]{2,49})')
            
            sip = None
            dip = None
            sport = None
            dport = None

            if not have_connection:
                m = re_packet_start.search(line)
                if m:
                    #print_yellow_bright("Packet start: " + line.strip())
                    sip = m.group(1)
                    dip = m.group(3)
                    sport = m.group(2)
                    dport = m.group(4)
                    #print_yellow_bright("%s:%s -> %s:%s" % (sip,sport,dip,dport))
                    have_connection = True

                    self.server_port = dport


            matched = False
            m = None
            
            if not matched:
                m = re_packet_content_client.search(line)
                if m:
                    #print_green_bright(line.strip())
                    #print_green(m.group(2))
                    this_packet_bytes.append(m.group(2))
                    this_packet_origin = 'client'
                    matched = True
            
            if not matched:
                m = re_packet_content_server.search(line)
                if m:
                    #print_red(m.group(2))
                    this_packet_bytes.append(m.group(2))
                    this_packet_origin = 'server'
                    matched = True
            
            if not matched:
                if this_packet_bytes:
                    #finalize packet


                    data = self.smcap_convert_lines_to_bytes(this_packet_bytes)
                    if this_packet_origin == 'client':
                        #print_green("# Converted: -->\n%s\n#<--" % (data,))
                        self.packets.append(data)
                        self.origins['client'].append(this_packet_index)
                    else:
                        #print_red("# Converted: -->\n%s\n#<--" % (data,))
                        self.packets.append(data)
                        self.origins['server'].append(this_packet_index)

                    this_packet_bytes = []
                    this_packet_origin = None
                    this_packet_index += 1


    def smcap_convert_lines_to_bytes(this, list_of_ords):
        bytes = ''
        
        for l in list_of_ords:
            for oord in l.split(" "):
                if oord:
                    bytes += binascii.unhexlify(oord)
                    
        return bytes

    def list_smcap(self):
        for line in fileinput.input(files=[self.fnm,]):
            re_packet_start = re.compile(r'^\+\d+: +\d+::([^:]+):([^:]+)-\d+::([^:]+):([^:(]+)')
           
            sip = None
            dip = None
            sport = None
            dport = None
            have_connection = False
            
            
            if not have_connection:
                m = re_packet_start.search(line)
                if m:
                    #print_yellow_bright("Packet start: " + line.strip())
                    sip = m.group(1)
                    dip = m.group(3)
                    sport = m.group(2)
                    dport = m.group(4)
                    print_yellow("%s:%s -> %s:%s  (single connection per file in smcap files)" % (sip,sport,dip,dport))
                    
                    return
                
    def export_script(self,efile):
        
        c  = "class PPlayScript:\n\n"
        c += "    def __init__(self,pplay):\n"
        c += "        # access to pplay engine\n"
        c += "        self.pplay = pplay\n\n"
        c += "        self.packets = []\n"
        for p in self.packets:
            c += "        self.packets.append(%s)\n\n" % repr(str(p),)
        
        c += "        self.origins = {}\n\n"
        c += "        self.server_port = %s\n" % (self.server_port,)
        for k in self.origins.keys():
            c+= "        self.origins['%s']=%s\n" % (k,self.origins[k])
            
        c+="\n\n"
        c+="""
    def before_send(self,role,index,data):
        # when None returned, no changes will be applied and packets[ origins[role][index] ] will be used
        return None

    def after_received(self,role,index,data):
        # return value is ignored: use it as data gathering for further processing
        return None
        """
        
        f = open(efile+".py",'w')
        f.write(c)
        f.close()

    # for spaghetti lovers
    def impersonate(self,who):
        if who == "client":
            self.impersonate_client()
        elif who == "server":
            self.impersonate_server()
    
    def send_aligned(self):
        
        if self.packet_index < len(self.origins[self.whoami]):
            return self.total_packet_index >= self.origins[self.whoami][self.packet_index]
        return False

    def send_issame(self):
        if self.packet_index < len(self.origins[self.whoami]):
            return self.packets[self.origins[self.whoami][self.packet_index]] == self.to_send
        return False
    
    def ask_to_send(self,xdata=None):
            
        data = None
        if xdata == None:
            data = self.to_send
        else:
            data = xdata
        
        aligned = ''
        if self.send_aligned():
            aligned = '(in-sync'
        
        if not self.send_issame():
            if aligned:
                aligned += ", modified"
            else:
                aligned += "(modified"
        
        if aligned:
            aligned+=") "
        
        print_yellow_bright("# [%d/%d]: %soffer to send -->" % (self.packet_index+1,len(self.origins[self.whoami]),aligned))
        out = hexdump(str(data))
        if aligned:
            print_green(out)
        else:
            print_yellow(out)
        print_yellow_bright("#<--")
        
        print_yellow_bright("#--> SEND IT TO SOCKET? [ y=yes (default) | s=skip | c=CR | l=LF | x=CRLF ]")
        print_yellow_bright("#    Advanced: r=replace (vim 's' syntax: r/<orig>/<repl>/<count,0=all>)")


    def ask_to_send_more(self):
        print_yellow_bright("#--> SEND MORE INTO SOCKET? [ c=CR | l=LF | x=CRLF ]")
        #print_yellow_bright("#    Advanced: r=replace (vim 's' syntax: r/<orig>/<repl>/<count,0=all>)")


    def prepare_socket(self, s, server_side=False):
        if have_ssl and self.use_ssl:
            if not server_side:
                return ssl.wrap_socket(s,ca_certs="certs/ca-cert.pem")
            else:
                return ssl.wrap_socket(s,
                                 server_side=True,
                                 certfile="certs/srv-cert.pem",
                                 keyfile="certs/srv-key.pem",
                                 ssl_version=ssl.PROTOCOL_TLSv1)                
        else:
            return s
                
        
    def impersonate_client(self):
        try:
            self.whoami = "client"
            
            print_white_bright("IMPERSONATING CLIENT, connecting to %s:%s" % (self.server_replaced_ip,self.server_port))
            
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s = self.prepare_socket(s,False)
            
            try:
                s.connect((self.server_replaced_ip,int(self.server_port)))
                self.packet_loop(s)
                
            except socket.error,e:
                print_white_bright("Connection to %s:%s failed: %s" % (self.server_replaced_ip, self.server_port, e))
                return
            
            
        except KeyboardInterrupt, e:
            print_white_bright("\nCtrl-C: bailing it out.")
            return
    
    def impersonate_server(self):
        global g_script_module
        
        try:
            self.whoami = "server"
            print_white_bright("IMPERSONATING SERVER, listening on %s" % (self.server_port,))
            
            server_address = ('0.0.0.0', int(self.server_port))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            s.bind(server_address)
            s.listen(1)

            while True:
                print ("waiting for new connection...")
                conn, client_address = s.accept()
                
                print ("accepted client from %s:%s" % (client_address[0],client_address[1]))
            
                conn = self.prepare_socket(conn,True)
            
                try:
                    if g_script_module:
                        self.scripter = g_script_module.PPlayScript(self)
                        self.load_scripter_defaults()          
                    
                    self.packet_loop(conn)
                except KeyboardInterrupt, e:
                    print_white_bright("\nCtrl-C: hit in client loop, exiting to accept loop. Hit Ctrl-C again to terminate.")
                    conn.close()
                except socket.error, e:
                    print_white_bright("\nConnection with %s:%s terminated: %s" % (client_address[0],client_address[1],e,))

                # reset it in both cases when Ctrl-C received, or connection was closed
                self.packet_index = 0
                self.total_packet_index = 0

        except KeyboardInterrupt, e:
            print_white_bright("\nCtrl-C: bailing it out.")
            return
        except socket.error, e:
            print_white_bright("Server error: %s" % (e,))



    def read(self,conn):
        if have_ssl and self.use_ssl:
            data = ''
            
            while True:
                try:
                    data = conn.recv(conn.pending())
                except ssl.SSLError as e:
                    # Ignore the SSL equivalent of EWOULDBLOCK, but re-raise other errors
                    if e.errno != ssl.SSL_ERROR_WANT_READ:
                        raise
                    continue

                except SystemError, e:
                    print_red_bright("read(): system error: %s" % (str(e),))

                data_left = conn.pending()
                while data_left:
                    data += conn.recv(data_left)
                    data_left = conn.pending()
                break
            
            self.tstamp_last_read = time.time()
            return data
        else:
            self.tstamp_last_read = time.time()
            return conn.recv(4096)

    def write(self,conn,data):
        
        if have_ssl and self.use_ssl:
            self.tstamp_last_write = time.time()
            return conn.write(data)
        else:
            self.tstamp_last_write = time.time()
            return conn.send(data)

    def load_to_send(self,role,role_index):
        who = self
        if self.scripter:
            who = self.scripter
            
        to_send_idx = who.origins[role][role_index]
        return who.packets[to_send_idx]        
    

    def send_to_send(self,conn):
        self.packet_index += 1
        self.total_packet_index += 1

        total_data_len = len(self.to_send)
        total_written = 0

        while total_written != total_data_len:
            cnt = self.write(conn,(str(self.to_send)))
            
            # not really clean debug, lots of data will be duplicated
            # if cnt > 200: cnt = 200
            
            data_len = len(self.to_send)

            if cnt == data_len:
                print_green_bright("# %s [%d/%d]: has been sent (%d bytes)" % (str_time(),self.packet_index,len(self.origins[self.whoami]),cnt))
            else:
                print_green_bright("# %s [%d/%d]: has been sent (ONLY %d/%d bytes)" % (str_time(),self.packet_index,len(self.origins[self.whoami]),cnt,data_len))
                self.to_send = str(self.to_send)[cnt:]
            
            total_written += cnt

        self.to_send = None
        
        

    def select_wrapper(self,conn,no_writes):
        
        inputs = [conn,sys.stdin]
        outputs = [conn]    
        if no_writes:
            outputs.remove(conn)
        
        if have_ssl and self.use_ssl:
            r = []
            w = []
            e = []
            
            if conn.pending(): r.append(conn)   # if there are bytes,
            
            if not no_writes:
                w.append(conn)                      # FIXME: we assume we can always write without select
            
            rr,ww,ee = select(inputs,outputs,[],0.2)
            if conn in rr:
                r.append(conn)
            if sys.stdin in rr:
                r.append(sys.stdin)
                
            return r,w,e
            
        else:

            return  select(inputs,outputs,[],0.2)

    def packet_loop(self,conn):
        global option_auto_send

        running = 1        
        write_end = False
        auto_send_now = time.time()
        
        
        while running:
            time.sleep(0.2)
            #print_red(".")
            r,w,e = self.select_wrapper(conn,write_end)
            
            if conn in r:
                d = self.read(conn)
                if not len(d):
                    print_red_bright("#--> connection closed by peer")
                    break

                
                # there are still some data to send/receive
                if self.total_packet_index < len(self.packets):
                    # test if data are as we should expect
                    aligned = False
                    
                    # if auto is enabled, we will not wait for user input when we received already some packet
                    # user had to start pplay on the other side
                    if option_auto_send:
                        auto_send_now = time.time()
                    
                    # to print what we got and what we expect
                    #print_white_bright(hexdump(d))
                    #print_white_bright(hexdump(str(self.packets[self.total_packet_index])))

                    scripter_flag = ""
                    if self.scripter:
                            scripter_flag = " (sending to script)"
                    
                    if str(d) == str(self.packets[self.total_packet_index]):
                        aligned = True
                        self.total_packet_index += 1
                        print_red_bright("# %s: received %dB OK%s" % (str_time(),len(d),scripter_flag))
                    
                    else:
                        smatch = difflib.SequenceMatcher(None, str(d), str(self.packets[self.total_packet_index-1]),autojunk=False)
                        qr = smatch.ratio()
                        if qr > 0.05:
                            print_red_bright("# %s received %sB modified (%.1f%%)%s" % (str_time(),len(d),qr*100,scripter_flag))                    
                            self.total_packet_index += 1
                        else:
                            print_red_bright("# %s received %sB of different data%s" % (str_time(),len(d),scripter_flag))
                    
                    if self.scripter:
                        self.scripter.after_received(self.whoami,self.packet_index,str(d))
                        print_red_bright("# received data processed")
                    
                    # this block is printed while in the normal packet loop (there are packets still to receive or send
                    if aligned:
                        if option_dump_received_correct:
                            print_red_bright("#-->")
                            print_red(hexdump(d))
                            print_red_bright("#<--")
                    else:
                        if option_dump_received_different:
                            print_red_bright("#-->")
                            print_red(hexdump(d))
                            print_red_bright("#<--")

                # this block means there is nothing to send/receive
                else:
                    if option_dump_received_different:
                        print_red_bright("#-->")
                        print_red(hexdump(d))
                        print_red_bright("#<--")
                
                # we have already data to send prepared!
                if self.to_send:
                    #  print, but not block
                    self.ask_to_send(self.to_send)
                else:
                    self.ask_to_send_more()
        
            if conn in w:
            
                if self.packet_index >= len(self.origins[self.whoami]):
                    print_yellow_bright("# Nothing left to send, hit Ctrl-C to interrupt whenever needed.")
                    print_yellow_bright("# [EOT]")
                    self.ask_to_send_more()
                    # if we have nothing to send, remove conn from write set
                    self.to_send = None
                    write_end = True
                    continue
                else:
                    
                    if not self.to_send:
                        self.to_send = self.load_to_send(self.whoami,self.packet_index)
                        
                
                        to_send_2 = None
                        if self.scripter:
                            to_send_2 = self.scripter.before_send(self.whoami,self.packet_index,str(self.to_send))
                            if to_send_2 != None:
                                print_yellow_bright("# data modified by script!")
                                self.to_send = to_send_2
                            
                        self.ask_to_send(self.to_send)
                    else:
                        if sys.stdin in r:
                            l = sys.stdin.readline()
                            #print("# --> entered: '" + l + "'")
                            self.process_command(l.strip(),'ysclxri',conn)

                            # in auto mode, reset current state, since we wrote into the socket
                            if option_auto_send:
                                auto_send_now = time.time()
                                continue


                        # auto_send feature
                        if option_auto_send > 0 and self.send_aligned():
                            
                            now = time.time()
                            if self._last_countdown_print == 0:
                                self._last_countdown_print = now
                            

                            delta = now - self._last_countdown_print
                            # print out the dot
                            if delta >= 1:
                                print(".",end='')
                                self._last_countdown_print = now                            

                            if now - auto_send_now >= option_auto_send:
                                print_green_bright(" -> sending!")
                                self.send_to_send(conn)
                                auto_send_now = now


            if write_end and sys.stdin in r:
                l = sys.stdin.readline()
                self.process_command(l.strip(),'clx',conn)

                if self.to_send:
                    self.ask_to_send()
                else:
                    self.ask_to_send_more()

    def replace(self,command,data):
        # something like vim's replace:  r/something/smtelse/0
        
        if len(command) > 1:
            
            parts = command.split(command[1])
            print_yellow(str(parts))
            if len(parts) == 4:
                return re.sub(parts[1],parts[2],str(data),int(parts[3]),flags=re.MULTILINE)
            else:
                return None

        return None

    def process_command(self,l,mask,conn):
        global option_auto_send
        
        if l == '':
            l = 'y'
        
        if l in mask and (l.startswith("y")):
            self.send_to_send(conn)
            
            if self.packet_index == len(self.origins[self.whoami]):
                print_green_bright("# %s [%d/%d]: that was our last one!!" % (str_time(),self.packet_index,len(self.origins[self.whoami])))
            
        elif l in mask and l.startswith('s'):
            self.packet_index += 1                                
            self.to_send = None
            print_green_bright("# %s [%d/%d]: has been SKIPPED" % (str_time(),self.packet_index,len(self.origins[self.whoami])))

        elif l in mask and l.startswith('c'):
            self.to_send = None # to reinit and ask again
            cnt = self.write(conn,"\n")
            print_green_bright("# %s custom '\\n' payload (%d bytes) inserted" % (str_time(),cnt,))

        elif l in mask and l.startswith('l'):
            self.to_send = None # to reinit and ask again
            cnt = self.write(conn,"\r")
            print_green_bright("# %s custom '\\r' payload (%d bytes) inserted" % (str_time(),cnt,))

        elif l in mask and l.startswith('x'):
            self.to_send = None # to reinit and ask again
            cnt = self.write(conn,"\r\n")
            print_green_bright("# %s custom '\\r\\n' payload (%d bytes) inserted" % (str_time(),cnt,))

        elif l in mask and l.startswith('r'):
            ret = self.replace(l.strip(),self.to_send)
            if ret:
                self.to_send = ret
                print_yellow_bright("# %s custom payload created (%d bytes)" % (str_time(),len(self.to_send),))
                self.ask_to_send(self.to_send)
            else:
                print_yellow_bright("# Failed to create custom payload")
        elif l in mask and l.startswith('i'):
            option_auto_send = (-1 * option_auto_send)
            if option_auto_send > 0:
                print_yellow_bright("# Toggle automatic send: enabled, interval %d" % (option_auto_send,))
            else:
                print_yellow_bright("# Toggle automatic send: disabled")        


def main():
    global option_auto_send, g_script_module
    
    if have_colorama:
        colorama.init(autoreset=True)


    parser = argparse.ArgumentParser(
        description=title,
        epilog=" - %s " % (copyright,) )

    ds = parser.add_argument_group("Data Sources")
    group1 = ds.add_mutually_exclusive_group()
    group1.add_argument('--pcap', nargs=1, help='pcap where the traffic should be read (retransmissions not checked)')
    group1.add_argument('--smcap', nargs=1, help='textual capture taken by smithproxy')
    group1.add_argument('--script', nargs=1, help='EXPERIMENTAL: load python script previously generated by --export command; Expect API changes.')


    ac = parser.add_argument_group("Actions")
    group2 = ac.add_mutually_exclusive_group()
    group2.add_argument('--client', nargs=1, help='replay client-side of the CONNECTION, connect and send it to specified IP address')
    group2.add_argument('--server', action='store_true', help='listen on socket and replay server part of the connection to incoming connections')
    group2.add_argument('--list', action='store_true', help='rather than act, show to us list of connections in the specified sniff file')
    group2.add_argument('--export', nargs=1, help='take capture file and export it to python script according CONNECTION parameter')

    ac_sniff = parser.add_argument_group("Filter on sniffer filtes (mandatory unless --script is used)")
    ac_sniff.add_argument('--connection', nargs=1, help='replay/export specified connection; use format <src_ip>:<sport>. IMPORTANT: it\'s SOURCE based to match unique flow!')

    var = parser.add_argument_group("Various")
    var.add_argument('--ssl', required=False, action='store_true', help='toggle this flag to wrap payload to SSL')
    var.add_argument('--version', required=False, action='store_true', help='just print version and terminate')
    auto_group = var.add_mutually_exclusive_group()
    auto_group.add_argument('--noauto', required=False, action='store_true', help='toggle this to confirm each payload to be sent')
    auto_group.add_argument('--auto', nargs='?',required=False, type=int, default=5, help='let %(prog)s to send payload automatically each AUTO seconds (default: %(default)s)')
    

    args = parser.parse_args(sys.argv[1:])

    if args.version:
        print_white_bright(pplay_version)
        sys.exit(0)

    print_white_bright(title)
    print_white(copyright)
    print("")

    r = None
    if args.pcap:
        r = Repeater(args.pcap[0],"")
    elif args.smcap:
        r = Repeater(args.smcap[0],"")
    elif args.list:
        pass
    elif args.script:
        r = Repeater(None,"")
    else:
        print_red_bright("error: no file to parse!")
        sys.exit(-1)


    if args.list:
        if args.smcap:
            r.list_smcap()
        elif args.pcap:
            r.list_pcap()
            
        sys.exit(0)


    # content is controlled by script
    if args.script:
        try:
            # add current directory into PYTHONPATH
            sys.path.append(os.getcwd())
            
            # if there is path specified in the script filename, add it to PYTHONPATH too
            if os.path.dirname(args.script[0]) != '':
                sys.path.append(os.path.dirname(args.script[0]))
                
            print_white_bright("Loading custom script: %s (pwd=%s)" % (args.script[0],os.getcwd()))
            g_script_module = __import__(os.path.basename(args.script[0]),globals(),locals(),[],-1)

            r.scripter = g_script_module.PPlayScript(r)
            r.load_scripter_defaults()
        
        except ImportError, e:
            print_red_bright("Error loading script file: %s" % (str(e),))
            #print_red(pprint.pformat(sys.))
            sys.exit(-2)
        except AttributeError, e:
            print_red_bright("Error loading script file: %s" % (str(e),))
            sys.exit(-2)

    if args.export or args.client or args.server:
        if args.connection:
            l = args.connection[0].split(":")
            im_ip = None
            im_port = None
            
            if len(l) != 2:
                print_red_bright("error: connection syntax!")
                sys.exit(-1)

            im_ip = l[0]
            im_port = l[1]
                
            if args.smcap:
                r.read_smcap(im_ip,im_port)
            elif args.pcap:
                r.read_pcap(im_ip,im_port)        
        
        # we have to have data available, unless controlled by script
        elif not args.script:
            print_white_bright("--connection argument has to be set for this option")
            sys.exit(-1)
        
        # cannot collide with script - those are in the exclusive argparse group
        if args.export:   
            export_file = args.export[0]
            r.export_script(export_file)
            print_white_bright("Template python script has been exported to file %s.py" % (export_file,))
            sys.exit(0)

        # ok regardless data controlled by script or capture file read
        elif args.client or args.server:
            if args.ssl:
                if not have_ssl:
                    print_red_bright("error: SSL not available!")
                    sys.exit(-1)
                
                r.use_ssl = True

            if args.noauto:
                option_auto_send = -1
            elif args.auto:
                option_auto_send = int(args.auto)
            else:
                # option_auto_send = 5
                pass
            
            
            if args.client:
                r.server_replaced_ip = args.client[0]
                r.impersonate('client')
            elif args.server:
                r.impersonate('server')

    else:
        print_white_bright("No-op! You wanted probably to set either --client <target_server_ip> or --server arguments ... Hmm?")

    #parser.print_help()


if __name__ == "__main__":
    main()
