# Criar CA (Certificate Authority)
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 365 -key ca.key -out ca.crt -subj "/CN=IoT-CA"

# Criar certificado do broker
openssl genrsa -out broker.key 2048
openssl req -new -key broker.key -out broker.csr -subj "/CN=localhost"
openssl x509 -req -days 365 -in broker.csr -CA ca.crt -CAkey ca.key \
        -CAcreateserial -out broker.crt