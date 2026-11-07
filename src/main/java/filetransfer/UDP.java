package src.main.java.filetransfer;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import src.main.java.common.*;

public class UDP {
    public UDP() {};
    public void send(
        int version, 
        int messageType, 
        int flags, 
        int streamID, 
        int senderID, 
        int receiverID, 
        byte[][] payloads, 
        InetAddress destIp, 
        int destPort
    ) throws IOException {
        DatagramSocket socket = new DatagramSocket();
        socket.setSoTimeout(1000); 
        
        byte seqNum = 0x00;
        for (byte[] payload : payloads) {
            PacketHeader header = new PacketHeader(
                version, 
                messageType, 
                flags, 
                streamID, 
                seqNum,
                payload.length, 
                senderID, 
                receiverID
            );
            Packet packet = new Packet(header, payload);
            byte[] encodededPacket = PacketCodec.encode(packet);
            DatagramPacket sendPacket = new DatagramPacket(encodededPacket, encodededPacket.length, destIp, destPort);

            boolean isAcked = false;
            int retries = 0;
            boolean doSend = true;
            while (!isAcked && retries < 10) {
                if(doSend) socket.send(sendPacket);
                
                try {
                    DatagramPacket receivedAck = new DatagramPacket(new byte[24], 24);
                    socket.receive(receivedAck);
                    
                    Packet ack = PacketCodec.decode(receivedAck.getData());
                    int receivedSeqNum = ack.getHeader().getSequenceNumber();
                    
                    if (receivedSeqNum == seqNum) {
                        seqNum = (byte) (seqNum == 0x00 ? 0x01 : 0x00);
                        isAcked = true;
                    } else {
                        doSend = false;
                    }
                    
                } catch (SocketTimeoutException e) {
                    doSend = true;
                    retries++;
                }
            }
            
            if (!isAcked) {
                System.out.println("Đã thử gửi 10 lần nhưng không nhận được phản hồi.");
                break; 
            }
        }
        socket.close();
    }
    public void receive(int totalPackets,  InetAddress destIp, int destPort) throws IOException {
        DatagramSocket socket = new DatagramSocket();
        Packet[] packets = new Packet[totalPackets];
        
        byte seqNum = 0x01;
        for(int i = 0; i < totalPackets; i++) {
            DatagramPacket receivedPacket = new DatagramPacket(new byte[24], 24);
            socket.receive(receivedPacket); 
            Packet data = PacketCodec.decode(receivedPacket.getData());
     
            int receivedSeqNum = data.getHeader().getSequenceNumber();
            if (receivedSeqNum == seqNum) {
                packets[i] =  data;
                seqNum = (byte) (seqNum == 0x00 ? 0x01 : 0x00);
            }

            PacketHeader header = new PacketHeader(
                2, // version, 
                0x04, // messageType ACK
                0, // flags, 
                0, // streamID, 
                receivedSeqNum, // seqNum, 
                0, // payload.length, 
                0, // senderID, 
                0 // receiverID
            );
            Packet packet = new Packet(header, null);

            byte[] ack = PacketCodec.encode(packet);
            // Gửi ACK về sender
            DatagramPacket ackPacket = new DatagramPacket(ack, ack.length, destIp, destPort);
            socket.send(ackPacket);
        }

        socket.close();
    }
}