"""
PQC OTA Server - MQTT Broker Integration
양자 내성 암호화를 적용한 MQTT 통신
"""

import paho.mqtt.client as mqtt
import json
import os
from datetime import datetime
from typing import Callable, Optional

# 설정
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 8883
CERT_DIR = os.path.join(os.path.dirname(__file__), '../certs')


class PQCMQTTClient:
    """PQC TLS를 사용하는 MQTT 클라이언트"""
    
    def __init__(
        self,
        client_id: str = "ota_server",
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
        ca_file: Optional[str] = None
    ):
        self.client = mqtt.Client(client_id=client_id)
        self.cert_file = cert_file or os.path.join(CERT_DIR, "server.crt")
        self.key_file = key_file or os.path.join(CERT_DIR, "server.key")
        self.ca_file = ca_file or os.path.join(CERT_DIR, "ca.crt")
        
        # 콜백
        self.on_device_status: Optional[Callable] = None
        self.on_update_progress: Optional[Callable] = None
        self.on_update_result: Optional[Callable] = None
        
        # 콜백 설정
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
    
    def connect(self, host: str = MQTT_BROKER_HOST, port: int = MQTT_BROKER_PORT):
        """MQTT 브로커에 연결"""
        # TLS 설정
        self.client.tls_set(
            ca_certs=self.ca_file,
            certfile=self.cert_file,
            keyfile=self.key_file
        )
        
        # TLS 1.3 사용 (OpenSSL 1.1.1+ 필요)
        # self.client.tls_insecure_set(False)
        
        try:
            self.client.connect(host, port, keepalive=60)
            self.client.loop_start()
            print(f"[MQTT] Connected to {host}:{port}")
        except Exception as e:
            print(f"[MQTT] Connection failed: {e}")
            raise
    
    def disconnect(self):
        """연결 종료"""
        self.client.loop_stop()
        self.client.disconnect()
        print("[MQTT] Disconnected")
    
    def _on_connect(self, client, userdata, flags, rc):
        """연결 콜백"""
        if rc == 0:
            print("[MQTT] Connection successful")
            
            # 토픽 구독
            self.client.subscribe("ota/device/+/status", qos=1)
            self.client.subscribe("ota/device/+/progress", qos=0)
            self.client.subscribe("ota/device/+/result", qos=2)
            
            print("[MQTT] Subscribed to device topics")
        else:
            print(f"[MQTT] Connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """연결 해제 콜백"""
        print(f"[MQTT] Disconnected (rc={rc})")
    
    def _on_message(self, client, userdata, msg):
        """메시지 수신 콜백"""
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        
        print(f"[MQTT] Message: {topic} -> {payload}")
        
        try:
            data = json.loads(payload)
            
            # 디바이스 상태
            if '/status' in topic:
                if self.on_device_status:
                    self.on_device_status(topic, data)
            
            # 다운로드 진행률
            elif '/progress' in topic:
                if self.on_update_progress:
                    self.on_update_progress(topic, data)
            
            # 업데이트 결과
            elif '/result' in topic:
                if self.on_update_result:
                    self.on_update_result(topic, data)
        
        except json.JSONDecodeError:
            print(f"[MQTT] Invalid JSON: {payload}")
    
    def publish_update_notification(self, version: str, is_critical: bool = False):
        """업데이트 알림 발행"""
        payload = json.dumps({
            'version': version,
            'is_critical': is_critical,
            'timestamp': datetime.now().isoformat()
        })
        
        self.client.publish("ota/update/available", payload, qos=1, retain=False)
        print(f"[MQTT] Published update notification: {version}")
    
    def publish_message(self, topic: str, payload: dict, qos: int = 1):
        """메시지 발행"""
        payload_str = json.dumps(payload)
        self.client.publish(topic, payload_str, qos=qos)
        print(f"[MQTT] Published to {topic}")


# 예제 사용법
if __name__ == '__main__':
    # MQTT 클라이언트 생성
    mqtt_client = PQCMQTTClient()
    
    # 콜백 설정
    def on_status(topic, data):
        print(f"Device status: {data}")
    
    def on_progress(topic, data):
        print(f"Update progress: {data.get('progress', 0)}%")
    
    def on_result(topic, data):
        print(f"Update result: {'Success' if data.get('success') else 'Failed'}")
    
    mqtt_client.on_device_status = on_status
    mqtt_client.on_update_progress = on_progress
    mqtt_client.on_update_result = on_result
    
    # 연결
    mqtt_client.connect()
    
    # 업데이트 알림
    mqtt_client.publish_update_notification("1.2.3", is_critical=True)
    
    # 메인 루프
    try:
        input("Press Enter to exit...\n")
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.disconnect()



