= Introdução e Objetivos

A proliferação de dispositivos no âmbito da Internet of Things (IoT) tem conduzido a um crescimento substancial do volume e diversidade de tráfego gerado nas infraestruturas de rede contemporâneas. Estes dispositivos suportam um espectro alargado de aplicações — desde sistemas de domótica e monitorização ambiental até automação industrial e infraestruturas de cidades inteligentes — gerando padrões de comunicação heterogéneos que colocam desafios significativos à gestão de redes, à garantia de Qualidade de Serviço (QoS) e à monitorização de segurança @atzori2010.

Para assegurar a confidencialidade e integridade das comunicações, as implementações IoT recorrem crescentemente a protocolos de encriptação como o Transport Layer Security (TLS) e o Datagram Transport Layer Security (DTLS). Estes mecanismos são fundamentais do ponto de vista da segurança e da privacidade dos utilizadores, impedindo o acesso não autorizado ao conteúdo dos pacotes transmitidos. Contudo, a adoção generalizada de encriptação reduz drasticamente a visibilidade do tráfego para os operadores de rede, tornando ineficazes as técnicas tradicionais de análise como a identificação baseada em portos ou a Deep Packet Inspection (DPI) @finsterbusch2014.

#figure(
  image("../architecture_passive.svg", width: 95%),
  caption: [Arquitetura do sistema de classificação passiva de tráfego IoT encriptado. O pipeline opera exclusivamente sobre metadados das camadas de rede e transporte, sem qualquer inspeção de payload.],
) <fig-architecture>

Não obstante a encriptação do payload, o tráfego de rede continua a expor características observáveis nas camadas de rede e transporte. Propriedades como a distribuição de tamanhos de pacotes, os intervalos temporais entre transmissões consecutivas (Inter-Arrival Time), a duração dos fluxos e o volume total de dados transferido permanecem acessíveis a um observador passivo posicionado na infraestrutura de rede. Investigações anteriores demonstraram que estas features estatísticas e comportamentais podem ser exploradas para classificar tráfego encriptado através de técnicas de Machine Learning, sem necessidade de aceder ao conteúdo cifrado @rezaei2019 @valdez2019.

Neste contexto, o presente projeto investiga a viabilidade de classificar e caracterizar tráfego IoT encriptado utilizando exclusivamente features observáveis ao nível da rede e do fluxo. Concretamente, o estudo centra-se em tráfego MQTT protegido por TLS, gerado num ambiente controlado com três classes representativas de comportamento IoT: telemetria periódica, mensagens event-driven e transferências de firmware (OTA). A classificação é realizada com base em seis features extraídas passivamente — nomeadamente a contagem de pacotes, o tamanho médio dos pacotes, o desvio padrão do tamanho, o tempo médio entre pacotes, o desvio padrão do inter-arrival time e o volume total de bytes — sem qualquer forma de inspeção ou desencriptação de payload.

#figure(
  image("../system_flow.svg", width: 95%),
  caption: [Pipeline de classificação: do pacote encriptado à decisão do modelo. O mesmo NFStream com `active_timeout=10s` é usado no treino offline e na inferência live, garantindo consistência entre pipelines.],
) <fig-pipeline>

== Objetivos Específicos

Os objetivos específicos do projeto são:

+ *Identificar classes representativas de tráfego IoT* com padrões de comunicação distintos ao nível da camada de transporte, mesmo sob encriptação TLS.

+ *Extrair e analisar features de rede e fluxo* que permaneçam observáveis independentemente da encriptação do payload, avaliando a sua capacidade discriminativa através de testes estatísticos (ANOVA, Cohen's d) e métricas de importância do modelo.

+ *Avaliar a separabilidade das classes de tráfego sob encriptação*, determinando em que medida os padrões comportamentais dos dispositivos IoT são distinguíveis a partir de metadados da camada de transporte.

+ *Analisar a robustez da classificação perante condições adversas de rede*, incluindo latência adicional e perda de pacotes, verificando se o modelo mantém a sua eficácia em cenários que simulam redes reais com degradação.

+ *Discutir as implicações para a gestão de redes, monitorização de segurança e privacidade dos utilizadores*, nomeadamente o que um observador passivo pode inferir sobre o comportamento dos dispositivos a partir de metadados de rede, mesmo quando todo o conteúdo está cifrado.

== Enquadramento e Abordagem

O foco da análise recai deliberadamente sobre a relevância e interpretabilidade das features — compreender _quais_ características do tráfego são mais informativas e _porquê_ — em detrimento da mera maximização de métricas de accuracy. Esta abordagem alinha-se com o enquadramento do projeto nas áreas de QoS e Gestão de Redes, onde a compreensão dos padrões de tráfego é tão relevante quanto a capacidade de os classificar automaticamente.

A @fig-architecture apresenta a arquitetura completa do sistema, organizada em quatro camadas funcionais: geração de tráfego (dispositivos IoT simulados via Docker), captura passiva (NFStream), classificação (Random Forest) e visualização (dashboard Flask). A @fig-pipeline detalha o fluxo de dados desde o pacote encriptado até à decisão do classificador, evidenciando a separação entre o que é cifrado (payload MQTT) e o que permanece observável (cabeçalhos TCP/IP e estatísticas de fluxo).
