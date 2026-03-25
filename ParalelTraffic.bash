# Captura na interface loopback, porta 8883 (MQTT/TLS)
# Corre ANTES de lançar o gerador Python!

sudo tshark -i lo -f "tcp port 8883" \
    -w captures/telemetry_$(date +%s).pcap \
    -a duration:120