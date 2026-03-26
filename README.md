# Analisador Passivo de Tráfego IoT (NFStream + Scikit-Learn)

Este projeto implementa um sistema de análise e classificação passiva de tráfego IoT (telemetria, eventos e atualizações de *firmware*) recorrendo a *Machine Learning*. O sistema extrai e analisa as métricas de rede sem necessidade de desencriptar a cifra TLS que protege o conteúdo das mensagens MQTT em topa.

## 🛠 Pré-requisitos
- Docker
- Docker Compose

## 🚀 Como Correr o Projeto

1. **Iniciar a aplicação**
   Na raiz do diretório do projeto (onde se encontra o ficheiro `docker-compose.yml`), abre um terminal e executa o seguinte comando para inicializar todos os contentores:
   ```bash
   docker compose up -d --build
   ```
   *Nota: se estiveres a usar a versão mais antiga do docker, usa `docker-compose` com o hífen.*

2. **O que é inicializado?**
   O Docker iniciará os seguintes serviços (em rede fechada `iot-net`):
   - **`broker`**: Servidor MQTT (Mosquitto) a escutar na porta 8883 (TLS seguro).
   - **`iot-device-1`, `iot-device-2`, `iot-device-3`**: Dispositivos IoT simulados que publicam tráfego distinto para o broker (respetivamente: fluxos contínuos de telemetria, tráfego *event-driven* esporádico e tráfego associado a downloads de *firmware*).
   - **`ai-server`**: O servidor principal de IA. Corre em modo privilegiado para observar passivamente o tráfego de interface usando `nfstream`. Agrupa os pacotes em fluxos, extraindo estatísticas da sua latência/tamanho e alimenta-as ao modelo que grava a inferência numa simples BD em SQLite.
   - **`dashboard`**: Uma interface web desenhada em Flask que lê os resultados da BD e mostra as classificações ao vivo.

3. **Aceder à Interface do Dashboard**
   Com os servidores a decorrer de forma funcional, abre o teu browser preferido e acede ao portal local:
   🔗 **[http://localhost:8080](http://localhost:8080)**

   🔒 **Password de Acesso**: `iot2025`

4. **Desligar o sistema**
   Quando quiseres interromper a operação e desativar todos os componentes para libertar os recursos, basta correr:
   ```bash
   docker compose down
   ```

## 🧠 Modelos de IA Treinados
Os modelos principais usados para classificar o tráfego (gerados pelo projeto) já se encontram previamente guardados na pasta `/data` (`model.joblib` e `binary_model.joblib`) no formato ideal (`joblib`) pronto a ser deserializado. Caso pretendas gerar os modelos novamente, poderás fazer a execução nativa de Python no ambiente através do dataset.
