"""
Reliable Transport Starter Code

This module contains the starter code for implementing reliable transport protocols.
Students should implement the SELECTIVE REPEAT protocol of sliding window.
"""

from queue import Queue, Empty
from typing import Tuple
from socket import socket
from dataclasses import dataclass
import util
import time
import random
import collections

Address = Tuple[str, int]


@dataclass
class MessageSender:
    """
    DO NOT EDIT ANYTHING IN THIS CLASS

    Base class for sending messages over a socket.
    Handles the mechanics of sending a formatted packet to the receiver.
    """

    sock: socket
    receiver_addr: Address
    msg_id: int

    def send(self, packet: str):
        """
        Send a packet to the receiver.

        Args:
            packet (str): The packet to send.
        """
        self.sock.sendto(
            f"s:{str(self.msg_id)}:{packet}".encode("utf-8"), self.receiver_addr
        )


@dataclass
class ReliableMessageSender(MessageSender):
    """
    This class reliably delivers a message to a receiver.

    You have to implement the send_message and on_packet_received methods.

    You can use self.send(packet) to send a packet to the receiver.

    You can add as many helper functions as you want.
    """

    window_size: int

    def on_packet_received(self, packet: str):
        """
        TO BE IMPLEMENTED BY STUDENTS

        This method is invoked whenever a packet is received from the receiver.
        Ideally, only ACK packets should be received here.
        You would have to use a way to communicate these packets to the send_message method.
        One way is to use a queue: you can enqueue packets to it in this method, 
        and dequeue them in send_message.
        You can also use the timeout argument of a queue’s dequeue method 
        to implement timeouts in this assignment.
        You should immediately return from this method and not block.
        """
        # Lazy initialize the ACK queue if it doesn't exist.
        if not hasattr(self, "ack_queue"):
            self.ack_queue = Queue()
        self.ack_queue.put(packet)

    def send_message(self, message: str):
        """
        TO BE IMPLEMENTED BY STUDENTS

        This method reliably sends the provided message to the receiver 
        using a sliding window mechanism based on the Selective Repeat protocol with Cumulative ACKs 
        (We will not be using NACKS). A complete transmission begins with a 'start' packet 
        and ends with an 'end' packet.
        Note that this method is allowed to block until the entire message is reliably transmitted.

        Sender Logic:
        1) Break the message into chunks of size util.CHUNK_SIZE.
        2) Choose a random sequence number as the starting point for the communication.
        3) Reliably send a 'start' packet by waiting for its ACK 
         (resending the packet if the ACK is not received within util.TIME_OUT seconds).
        4) Send out a window of data packets (the window size is provided via the 
         ReliableMessageSender constructor) and wait for 
         cumulative ACKs from the receiver to slide the window appropriately.
        5) If no ACKs are received for util.TIME_OUT seconds, 
         resend all packets in the current window.
        6) Once all data chunks have been reliably sent, 
         reliably send an 'end' packet (again waiting for its ACK).
        7) Note: Only data packets are transmitted using the sliding window mechanism; 
         the 'start' and 'end' packets are sent separately with their own reliability logic.
        """
        # Lazy initialize the ACK queue if needed.
        if not hasattr(self, "ack_queue"):
            self.ack_queue = Queue()

        # 1) Break the message into chunks.
        chunks = [
            message[i : i + util.CHUNK_SIZE]
            for i in range(0, len(message), util.CHUNK_SIZE)
        ]
        # 2) Choose a random starting sequence number.
        base_seq_num = random.randint(1000, 9999)

        # 3) Reliably send the start packet.
        start_packet = util.make_packet("start", base_seq_num)
        attempts = 0
        while attempts < util.NUM_OF_RETRANSMISSIONS:
            self.send(start_packet)
            try:
                ack_packet = self.ack_queue.get(timeout=util.TIME_OUT)
                if util.validate_checksum(ack_packet):
                    ack_type, ack_seq_str, _, _ = util.parse_packet(ack_packet)
                    if ack_type == "ack" and int(ack_seq_str) == base_seq_num + 1:
                        break
            except Empty:
                attempts += 1
        else:
            return  # Failed to send start packet reliably

        # 4) Initialize sliding window variables.
        next_seq_num = base_seq_num + 1
        window_base = next_seq_num
        packets_in_flight = (
            collections.OrderedDict()
        )  # Maps sequence numbers to packet info.
        final_seq_num = base_seq_num + len(chunks)

        # 5) Send data packets using the sliding window.
        while window_base <= final_seq_num:
            # Fill the window.
            while next_seq_num < window_base + self.window_size and (
                next_seq_num - base_seq_num - 1
            ) < len(chunks):
                chunk_index = next_seq_num - base_seq_num - 1
                data_packet = util.make_packet(
                    "data", next_seq_num, chunks[chunk_index]
                )
                self.send(data_packet)
                packets_in_flight[next_seq_num] = {
                    "packet": data_packet,
                    "timestamp": time.time(),
                }
                next_seq_num += 1

            try:
                # Wait for an ACK.
                ack_packet = self.ack_queue.get(timeout=util.TIME_OUT)
                if not util.validate_checksum(ack_packet):
                    continue
                ack_type, ack_seq_str, _, _ = util.parse_packet(ack_packet)
                ack_seq_num = int(ack_seq_str)
                if ack_type == "ack":
                    # Remove all packets with sequence numbers less than the ACK.
                    for seq in list(packets_in_flight.keys()):
                        if seq < ack_seq_num:
                            packets_in_flight.pop(seq, None)
                    window_base = max(window_base, ack_seq_num)
            except Empty:
                # No ACK received: retransmit timed-out packets.
                current_time = time.time()
                for seq_num, info in list(packets_in_flight.items()):
                    if current_time - info["timestamp"] > util.TIME_OUT:
                        self.send(info["packet"])
                        packets_in_flight[seq_num]["timestamp"] = current_time

        # 6) Reliably send the end packet.
        end_seq_num = next_seq_num
        end_packet = util.make_packet("end", end_seq_num)
        attempts = 0
        while attempts < util.NUM_OF_RETRANSMISSIONS:
            self.send(end_packet)
            try:
                ack_packet = self.ack_queue.get(timeout=util.TIME_OUT)
                if util.validate_checksum(ack_packet):
                    ack_type, ack_seq_str, _, _ = util.parse_packet(ack_packet)
                    if ack_type == "ack" and int(ack_seq_str) == end_seq_num + 1:
                        break
            except Empty:
                attempts += 1
        else:
            return  # Failed to send end packet reliably


@dataclass
class MessageReceiver:
    """
    DO NOT EDIT ANYTHING IN THIS CLASS
    """

    sock: socket
    sender_addr: Address
    msg_id: int
    completed_message_q: Queue

    def send(self, packet: str):
        """
        Send a packet back to the sender.

        Args:
            packet (str): The packet to send.
        """
        self.sock.sendto(
            f"r:{str(self.msg_id)}:{packet}".encode("utf-8"), self.sender_addr
        )

    def on_message_completed(self, message: str):
        """
        Notify that a complete message has been received.

        Args:
            message (str): The complete message received.
        """
        self.completed_message_q.put(message)


@dataclass
class ReliableMessageReceiver(MessageReceiver):
    """
    This class reliably receives a message from a sender.
    You have to implement the on_packet_received method.
    You can use self.send(packet) to send a packet back to the sender, and will have to call
    self.on_message_completed(message) when the complete message is received.
    You can add as many helper functions as you want.
    """

    def on_packet_received(self, packet: str):
        """
        TO BE IMPLEMENTED BY STUDENTS

        This method is invoked whenever a packet is received from the sender. 
        It must process the packet quickly and return immediately without blocking. 
        You should inspect the packet, decide on the appropriate action, 
        and, if necessary, send a corresponding ACK packet back to the sender 
        using self.send(packet). When you determine that the sender has completely 
        transmitted the message, assemble the chunks and call self.on_message_completed(message) 
        with the complete message received.
        Receiver’s Logic:
        1) Validate the packet’s checksum. If the packet is corrupted, ignore it.
        2) Inspect the packet_type and sequence number.
        3) If the packet type is "start":
        - Prepare to store incoming data chunks in an appropriate data structure.
        - Immediately send an ACK to the sender with the sequence number equal to (received sequence number + 1).
        4) If the packet type is "data":
        - Store the packet in an appropriate data structure if it is not a duplicate. 
         This includes storing out-of-order packets for later reassembly.
        - Always send a cumulative ACK based on the highest contiguous sequence number received so far. 
         For example, if packets 0 through 10 have been received in order, 
          send an ACK for sequence number 11—even if some out-of-order packets 
           beyond this range have been received.
        5) If the packet type is "end":
        - Assemble all stored data chunks into the complete message.
        - Call self.on_message_completed(message) with the assembled message.
        - Send an ACK with the sequence number equal to (received sequence number + 1).
        """
        if not util.validate_checksum(packet):
            return

        packet_type, seq_num_str, msg_content, _ = util.parse_packet(packet)
        seq_num = int(seq_num_str)

        # Lazy initialize receiver state.
        if not hasattr(self, "transmission_started"):
            self.transmission_started = False

        if packet_type == "start":
            self.start_seq_num = seq_num
            self.highest_seq_num_in_order = seq_num
            self.received_chunks = {}
            self.transmission_started = True
            ack_packet = util.make_packet("ack", seq_num + 1)
            self.send(ack_packet)

        elif packet_type == "data" and self.transmission_started:
            if seq_num not in self.received_chunks:
                self.received_chunks[seq_num] = msg_content
            current = self.highest_seq_num_in_order
            while current + 1 in self.received_chunks:
                current += 1
            self.highest_seq_num_in_order = current
            ack_packet = util.make_packet("ack", self.highest_seq_num_in_order + 1)
            self.send(ack_packet)

        elif packet_type == "end" and self.transmission_started:
            sorted_chunks = [
                self.received_chunks[seq] for seq in sorted(self.received_chunks.keys())
            ]
            complete_message = "".join(sorted_chunks)
            self.on_message_completed(complete_message)
            ack_packet = util.make_packet("ack", seq_num + 1)
            self.send(ack_packet)
            self.transmission_started = False
