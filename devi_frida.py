#!/usr/sbin/python3

import argparse
import json
import sys
from pathlib import Path
from os import path
from time import sleep

import frida


class Devi:

    def __init__(self, binary, module, out_file, symbol, pid=None, kill=False, verbose=False, debug=False):
        self.binary = binary
        self.module = module
        self.out_file = out_file
        self.pid = pid
        self.session = None
        self.calls = list()
        self.error = False
        self.kill = kill
        self.verbose = verbose
        self.debug_level = debug
        self.symbol = symbol

    def load_script(self):
        absolute_path = path.join(sys.path[0], "devi_frida_tracer.js")
        script = self.session.create_script(
            Path(absolute_path).read_text() % (self.debug_level, self.module, self.symbol))

        def on_message(message, data):
            """handle messages send by frida"""
            self.debug("[{}] -> {}".format(message, data))
            if message["type"] == "error":
                self.error = True
                self.warn(" - Frida Error - " + message["description"])
                self.warn(message["stack"])
                self.warn("lineNuber: " + str(message["lineNumber"]) + 
                    ", columnNumber: " + str(message["columnNumber"]))
            elif message["type"] == "send":
                if "callList" in message["payload"]:
                    self.calls.extend(message["payload"]["callList"])
                elif "moduleMap" in message["payload"]:
                    pass
                elif "symbolMap" in message["payload"]:
                    pass
                elif "deviFinished" in message["payload"]:
                    self.log(message["payload"]["deviFinished"])
                elif "deviError" in message["payload"]:
                    # Some Error occoured
                    self.error = True
                    self.warn(" - Error - " + message["payload"]["deviError"])

        script.on("message", on_message)
        script.load()
        # only resume if spawed
        # if we resume before we load the script we can not intercept main 
        try:
            frida.resume(int(self.pid))
        except frida.InvalidArgumentError:
            pass

    def spawn_binary(self):

        if not self.pid:
            if self.binary[:2] == './':
                self.binary = self.binary[2:]

            self.pid = frida.spawn(self.binary)
            self.debug("Spawned binay {} with pid {}".format(self.binary, self.pid))
        self.pid = int(self.pid)
        self.session = frida.attach(self.pid)
        self.debug("Attached to process {}".format(self.pid))

        self.load_script()

        if self.error:
            self.warn("error")
            self.session.detach()
            self.info("An error occoured while attaching!")
            sys.exit(-1)

        self.log('Tracing binary press control-D to terminate....')

        sys.stdin.read()

        try:
            self.log('Detaching, this might take a second...')
            if self.kill:
                frida.kill(self.pid)
                self.log('Killing process {}'.format(self.pid))
            self.session.detach()
        except frida.ProcessNotFoundError:
            self.log('Process already terminated')
        self.debug("Call Overview:")
        self.debug(str(self.calls))

        with open(self.out_file, "w+") as self.out_file:
            result = dict()
            result["deviVersion"] = 0.1
            result["calls"] = self.calls
            json.dump(result, self.out_file)


    def info(self, message):
        if self.verbose or self.debug_level:
            print("[-] " + message)

    def debug(self, message):
        if self.debug_level:
            print("[+] " + message)

    def warn(self, message):
        print("[!] " + message)

    def log(self, message):
        print("[*] " + message)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Devirtualize Virtual Calls")
    parser.add_argument("-o", "--out-file",
                      help="Output location", required=True)
    parser.add_argument(
        "-m", "--module", help="Module to trace", required=True)

    parser.add_argument(
        "-p", "--pid", help="Attach to PID", required=False)

    parser.add_argument(
        "-s", "--symbol", help="Hook symbol, default main, either offset or mangled name!", required=False, default="main")

    parser.add_argument(
        "-v", "--verbose", help="Set verbose logging", required=False, action='store_true')
    parser.add_argument(
        "-vv", "--debug", help="Set debug logging", required=False, action='store_true')
    parser.add_argument(
        "-k", "--kill", help="Kill process after detach", required=False, action='store_true')

    # add -t thread option if there are threads and so..

    # TODO add verbosity
    parser.add_argument("cmdline", nargs=argparse.REMAINDER,
                      help="Command line for process to spawn, e.g. ls -lah")

    args = parser.parse_args()

    if args.cmdline:
        if (args.cmdline[0] != "--") and not args.pid:
            parser.print_help()
            exit(1)
        args.cmdline = args.cmdline[1:]
    elif not args.pid:
        parser.print_help()
        target = None
        exit(1)

    devi = Devi(args.cmdline, args.module, args.out_file, args.symbol, 
        args.pid, args.kill, args.verbose, args.debug)
    devi.spawn_binary()
