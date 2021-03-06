#!/usr/bin/env python3
# Copyright (c) 2014-2017 Daniel Kraft
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

# Test the "getauxblock" merge-mining RPC interface.

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import *

from test_framework import auxpow

class GetAuxBlockTest (BitcoinTestFramework):

  def run_test (self):
    # Generate a block so that we are not "downloading blocks".
    self.nodes[0].generate (1)

    # We used to compare to getblocktemplate, but this call is gone
    # now completely for merge-mining.

    # Verify data that can be found in another way.
    auxblock = self.nodes[0].getauxblock ()
    assert_equal (auxblock['chainid'], 1)
    assert_equal (auxblock['height'], self.nodes[0].getblockcount () + 1)
    assert_equal (auxblock['previousblockhash'], self.nodes[0].getblockhash (auxblock['height'] - 1))

    # Calling again should give the same block.
    auxblock2 = self.nodes[0].getauxblock ()
    assert_equal (auxblock2, auxblock)

    # If we receive a new block, the old hash will be replaced.
    self.sync_all ()
    self.nodes[1].generate (1)
    self.sync_all ()
    auxblock2 = self.nodes[0].getauxblock ()
    assert auxblock['hash'] != auxblock2['hash']
    assert_raises_jsonrpc(-8, 'block hash unknown', self.nodes[0].getauxblock,
                          auxblock['hash'], "x")

    # Invalid format for auxpow.
    assert_raises_jsonrpc(-1, None, self.nodes[0].getauxblock,
                          auxblock2['hash'], "x")

    # Invalidate the block again, send a transaction and query for the
    # auxblock to solve that contains the transaction.
    self.nodes[0].generate (1)
    addr = self.nodes[1].getnewaddress ()
    txid = self.nodes[0].sendtoaddress (addr, 1)
    self.sync_all ()
    assert_equal (self.nodes[1].getrawmempool (), [txid])
    auxblock = self.nodes[0].getauxblock ()
    target = auxpow.reverseHex (auxblock['_target'])

    # Compute invalid auxpow.
    apow = auxpow.computeAuxpow (auxblock['hash'], target, False)
    res = self.nodes[0].getauxblock (auxblock['hash'], apow)
    assert not res

    # Compute and submit valid auxpow.
    apow = auxpow.computeAuxpow (auxblock['hash'], target, True)
    res = self.nodes[0].getauxblock (auxblock['hash'], apow)
    assert res

    # Make sure that the block is indeed accepted.
    self.sync_all ()
    assert_equal (self.nodes[1].getrawmempool (), [])
    height = self.nodes[1].getblockcount ()
    assert_equal (height, auxblock['height'])
    assert_equal (self.nodes[1].getblockhash (height), auxblock['hash'])

    # Call getblock and verify the auxpow field.
    data = self.nodes[1].getblock (auxblock['hash'])
    assert 'auxpow' in data
    auxJson = data['auxpow']
    assert_equal (auxJson['index'], 0)
    assert_equal (auxJson['chainindex'], 0)
    assert_equal (auxJson['merklebranch'], [])
    assert_equal (auxJson['chainmerklebranch'], [])
    assert_equal (auxJson['parentblock'], apow[-160:])

    # Also previous blocks should have 'auxpow', since all blocks (also
    # those generated by "generate") are merge-mined.
    oldHash = self.nodes[1].getblockhash (100)
    data = self.nodes[1].getblock (oldHash)
    assert 'auxpow' in data

    # Check that it paid correctly to the first node.
    t = self.nodes[0].listtransactions ("", 1)
    assert_equal (len (t), 1)
    t = t[0]
    assert_equal (t['category'], "immature")
    assert_equal (t['blockhash'], auxblock['hash'])
    assert t['generated']
    assert t['amount'] >= Decimal ("25")
    assert_equal (t['confirmations'], 1)

    # Verify the coinbase script.  Ensure that it includes the block height
    # to make the coinbase tx unique.  The expected block height is around
    # 200, so that the serialisation of the CScriptNum ends in an extra 00.
    # The vector has length 2, which makes up for 02XX00 as the serialised
    # height.  Check this.
    blk = self.nodes[1].getblock (auxblock['hash'])
    tx = self.nodes[1].getrawtransaction (blk['tx'][0], 1)
    coinbase = tx['vin'][0]['coinbase']
    assert_equal ("02%02x00" % auxblock['height'], coinbase[0 : 6])

    # Ensure that the payout address is changed from one block to the next.
    addr1 = auxpow.getCoinbaseAddr (self.nodes[1], auxblock['hash'])
    newHash = auxpow.mineAuxpowBlock (self.nodes[0])
    self.sync_all ()
    addr2 = auxpow.getCoinbaseAddr (self.nodes[1], newHash)
    assert addr1 != addr2
    valid = self.nodes[0].validateaddress (addr1)
    assert valid['ismine']
    valid = self.nodes[0].validateaddress (addr2)
    assert valid['ismine']

if __name__ == '__main__':
  GetAuxBlockTest ().main ()
