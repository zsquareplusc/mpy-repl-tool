#!/usr/bin/env python
#
# (C) 2021 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
import sys
from serial.tools.miniterm import Miniterm, key_description


def main(serial_instance):
    if not hasattr(serial_instance, 'cancel_read'):
        # enable timeout for alive flag polling if cancel_read is not available
        serial_instance.timeout = 1

    miniterm = Miniterm(
        serial_instance,
        echo=False,
        filters=['direct'])
    miniterm.set_rx_encoding('utf-8')
    miniterm.set_tx_encoding('utf-8')

    sys.stderr.write('--- Patched Miniterm-MPY on {p.name}  {p.baudrate},{p.bytesize},{p.parity},{p.stopbits} ---\n'.format(
        p=miniterm.serial))
    sys.stderr.write('--- Quit: {} | Menu: {} | Help: {} followed by {} ---\n'.format(
        key_description(miniterm.exit_character),
        key_description(miniterm.menu_character),
        key_description(miniterm.menu_character),
        key_description('\x08')))

    miniterm.start()
    try:
        miniterm.join(True)
    except KeyboardInterrupt:
        pass
    sys.stderr.write("\n--- exit ---\n")
    miniterm.join()
    miniterm.close()

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    main()
