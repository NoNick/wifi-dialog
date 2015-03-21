#!/usr/bin/python3
import subprocess
import re
from dialog import Dialog

wifiInterface = "wlp4s0"
config_dir = "/etc/nets/"
dhcp_start = ["dhcpcd", wifiInterface]
dhcp_stop = ["killall", "dhcpcd"]
d_width = 70


class WifiEntry:
    essid = ""
    # in percents
    quality = 0
    signal = None
    frequency = None
    encryption = False
    # if config file already exists
    configured = False
    key = None

    def __init__(self, string):
        qual_str = re.search(r'Quality=[0-9]+/[0-9]+', string).group(0)
        qual = qual_str[8:].split('/')
        self.quality = int(qual[0]) * 100 / int(qual[1])
        en_str = re.search(r'Encryption key:[a-z]+', string).group(0)
        self.encryption = en_str.split(':')[1] == "on"
        self.essid = re.search(r'ESSID:\".*\"', string).group(0)[7:-1]

        self.signal = re.search(r'Signal level=.*', string).group(0)
        self.frequency = re.search(r'Frequency:.*', string).group(0)

        self.configured = subprocess.check_output(["find", config_dir, "-name", self.essid + ".conf"]) != b''

    # represents entry as a tuple suitable for dialog menu
    def menu_entry(self):
        return self.essid[0:d_width - 28], str(int(self.quality)) + "%" + ", " + (
            "Encrypted" if self.encryption else "Open") + (", saved" if self.configured else "")

    # generates text for config file
    def config(self):
        result = "network={\n"
        result += "\tssid=\"" + self.essid + "\"\n"
        if self.encryption:
            result += "\tpsk=\"" + self.key + "\"\n"
            # TODO: grab encryption data from iwlist
            result += "\tproto=WPA2\n\tkey_mgmt=WPA-PSK\n\tgroup=CCMP TKIP\n\tpairwise=CCMP TKIP\n"
        else:
            result += "\tkey_mgmt=NONE\n"
        result += "}\n"
        return result

    # gets an dialog and uses it for getting key from user
    def ask_for_key(self, d):
        result = d.inputbox("Key for " + self.essid)
        if result[0] == Dialog.OK:
            self.key = result[1]

    # shows info dialog, propose change key or delete config file
    def info_dialog(self, d):
        info = "ESSID: " + self.essid + "\n"
        if self.frequency is not None:
            info += self.frequency + "\n"
        info += "Quality = " + str(int(self.quality)) + "%\n"
        if self.signal is not None:
            info += self.signal + "\n"
        info += ("Encrypted" if self.encryption else "Open") + (", saved" if self.configured else "") + "\n"
        key_text = "Change key" if self.configured else "Set key"

        if self.configured:
            _choice = d.yesno(info, height=10, width=70, extra_button=self.encryption,
                              extra_label=key_text, cancel_label="Delete config file", ok_label="Back")
        else:
            _choice = d.msgbox(info, height=10, width=70, ok_label="Back")
        if _choice == Dialog.EXTRA:
            self.ask_for_key(d)
            self.info_dialog(d)
        elif _choice == Dialog.CANCEL:
            subprocess.Popen(["rm", "-rf", config_dir + self.essid + ".conf"])
            self.configured = False
            self.info_dialog(d)


# returns dict with (essid, WifiEntry) elemetns
def cells_list(cells_str):
    result = []
    for c in str(cells_str).split("Cell")[1:]:
        try:
            tmp = WifiEntry(c)
            result.append((tmp.essid, tmp))
        except Exception:
            print("Error occurred during processing following string: " + c)
    return dict(result)


cells_str = subprocess.check_output(["/sbin/iwlist", wifiInterface, "scan"])
d = Dialog(dialog="dialog")
d.set_background_title("Wifi Dialog")
cells = cells_list(cells_str)

exit_flag = False
while not exit_flag:
    cells_entries = []
    for c in cells.values():
        cells_entries.append(c.menu_entry())

    # width: 6 for borders, 22 for, rest for essid. Cut essid if need
    choice = d.menu("Results of scan", choices=sorted(cells_entries, key=lambda entry: entry[1], reverse=True),
                    extra_button=True, extra_label="Info", cancel_label="Exit", ok_label="Connect",
                    width=d_width, height=19, menu_height=12)

    if choice[0] == Dialog.OK:
        chosen = cells[choice[1]]
        if not chosen.configured:
            if chosen.encryption and chosen.key is None:
                chosen.ask_for_key(d)
            config_file = open(config_dir + chosen.essid + ".conf", 'w')
            config_file.write(chosen.config())
            config_file.close()

        subprocess.Popen(["killall", "wpa_supplicant"])
        subprocess.Popen(dhcp_stop)
        subprocess.Popen(["wpa_supplicant", "-i" + wifiInterface, "-c" + config_dir + chosen.essid + ".conf"])
        subprocess.Popen(dhcp_start)
        exit_flag = True
    elif choice[0] == Dialog.EXTRA:
        chosen = cells[choice[1]]
        chosen.info_dialog(d)
    else:
        exit_flag = True
