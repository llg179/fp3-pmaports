# SPDX-License-Identifier: MIT
# qrtrconst.py - QRTR control codes, copied from the kernel's
# include/uapi/linux/qrtr.h (enum qrtr_pkt_type).  Import these; do not retype
# them.
#
# ☠️☠️ THE HISTORY OF THIS FILE IS THE POINT.  Every earlier tool here guessed
# the enum and guessed it wrong, twice:
#
#     used     believed to be   actually is
#     ----     --------------   -----------
#      2       NEW_SERVER       HELLO
#      3       NEW_SERVER       BYE          <- the "fixed" value, still wrong
#      4       DEL_SERVER       NEW_SERVER
#
# The enum starts at DATA = 1, not 0.  So every "we published service X"
# measurement in this investigation actually sent a BYE from our node, which
# tells the name service our whole node died.  That is why:
#   * not one SNS_REG_GROUP request was ever served (nothing was published),
#   * the ADSP still "woke" (a BYE forces a DEL_SERVER cascade and a
#     re-announcement -- an edge, once per ADSP boot, exactly as observed),
#   * publishing the gate list appeared to delete the system's own daemons
#     (it did: one BYE kills every server on the node, not just colliding ones).
#
# Anything measured with the old constants has to be re-measured.
QRTR_NODE_BCAST = 0xFFFFFFFF
QRTR_PORT_CTRL = 0xFFFFFFFE

QRTR_TYPE_DATA = 1
QRTR_TYPE_HELLO = 2
QRTR_TYPE_BYE = 3
QRTR_TYPE_NEW_SERVER = 4
QRTR_TYPE_DEL_SERVER = 5
QRTR_TYPE_DEL_CLIENT = 6
QRTR_TYPE_RESUME_TX = 7
QRTR_TYPE_EXIT = 8
QRTR_TYPE_PING = 9
QRTR_TYPE_NEW_LOOKUP = 10
QRTR_TYPE_DEL_LOOKUP = 11

CTRL_NAME = {
    QRTR_TYPE_DATA: 'DATA', QRTR_TYPE_HELLO: 'HELLO', QRTR_TYPE_BYE: 'BYE',
    QRTR_TYPE_NEW_SERVER: 'NEW_SERVER', QRTR_TYPE_DEL_SERVER: 'DEL_SERVER',
    QRTR_TYPE_DEL_CLIENT: 'DEL_CLIENT', QRTR_TYPE_RESUME_TX: 'RESUME_TX',
    QRTR_TYPE_EXIT: 'EXIT', QRTR_TYPE_PING: 'PING',
    QRTR_TYPE_NEW_LOOKUP: 'NEW_LOOKUP', QRTR_TYPE_DEL_LOOKUP: 'DEL_LOOKUP',
}
