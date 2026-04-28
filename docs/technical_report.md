# Classification and Characterisation of Encrypted IoT Traffic Using Network-Level Features

**Eduardo Queirós** · **Francisco Mota** · **Tiago Campos**  
University of Minho — Department of Informatics  
Braga, Portugal

---

## Abstract

The widespread adoption of encryption protocols such as TLS in IoT deployments significantly reduces the visibility of network traffic for operators, making traditional inspection techniques ineffective. This report presents a system that classifies encrypted IoT traffic into three behavioural categories — periodic telemetry, event-driven messages, and firmware updates — using only observable network-level features, without accessing packet payloads. A controlled environment was built using Docker containers and a Mosquitto MQTT broker with TLS, where three simulated IoT devices generate distinct traffic patterns. Flow-level statistics are extracted passively using NFStream and fed to a Random Forest classifier, achieving 99.6% accuracy on a balanced dataset of 13,500 samples. Robustness under network degradation (delay up to 500ms, packet loss up to 20%) was evaluated using Linux tc netem. Results confirm that encrypted IoT traffic remains characterisable from transport-layer metadata alone, with significant implications for network management and user privacy.

---

## 1. Introduction

The rapid growth of the Internet of Things has resulted in billions of interconnected devices continuously exchanging data across communication networks [1]. These devices support a wide range of applications, from smart homes and healthcare systems to industrial automation and smart city infrastructures. As IoT ecosystems expand, the volume and diversity of network traffic increases significantly, creating new challenges for network monitoring, traffic management, and security analysis [2].

To protect sensitive data and user privacy, many IoT communications rely on encryption protocols such as Transport Layer Security (TLS) and Datagram Transport Layer Security (DTLS). These protocols provide confidentiality and integrity for transmitted data, preventing unauthorised access to packet contents. However, the increasing adoption of encryption also limits the visibility of network traffic, making traditional inspection techniques such as port-based identification or Deep Packet Inspection (DPI) less effective [3].

Despite the encryption of packet payloads, network traffic still exposes observable characteristics at lower protocol layers. Features such as packet size distributions, flow duration, and inter-arrival times can provide useful insights into communication behaviour without accessing encrypted content. Previous research has shown that these statistical and behavioural features can be used to classify encrypted traffic through machine learning techniques [4].

This project investigates the feasibility of classifying and characterising encrypted IoT traffic using only network-level features. By analysing observable properties of encrypted traffic flows collected in a controlled environment, the goal is to evaluate whether meaningful traffic patterns can be identified without accessing packet payloads, and to assess the robustness of this approach under varying network conditions.

---

## 2. System Architecture

The proposed solution is structured as a four-layer analysis pipeline, implemented entirely using containerised services orchestrated with Docker Compose.

### 2.1 Overview

The system runs on an isolated Docker bridge network (`iot-net`, subnet `172.20.0.0/24`) with the following components:

| Container | Role | IP |
|---|---|---|
| `iot-broker` | Mosquitto MQTT broker (TLS, port 8883) | 172.20.0.2 |
| `iot-device-1` | Simulated telemetry device | 172.20.0.10 |
| `iot-device-2` | Simulated event-driven device | 172.20.0.11 |
| `iot-device-3` | Simulated firmware update device | 172.20.0.12 |
| `iot-ai-server` | Passive traffic analyser (NFStream + ML) | shared with broker |
| `iot-dashboard` | Flask web interface | — |

The AI server shares the broker's network namespace (`network_mode: service:broker`) and uses `NET_RAW` capabilities to passively observe all traffic on `eth0` without any TLS decryption.

### 2.2 Layer A — Network Generation and Emulation

Three Docker containers simulate distinct IoT device behaviours, each assigned a fixed IP address. All communication is encrypted with TLS 1.2 over MQTT (port 8883), using a self-signed CA certificate. The fixed IP addresses serve as ground truth labels — device identity is inferred from the source IP without inspecting any payload content.

Network degradation is applied using Linux Traffic Control (`tc netem`) via the Docker SDK, allowing controlled injection of latency and packet loss to evaluate classifier robustness.

### 2.3 Layer B — Processing and Feature Extraction

NFStream [5] is used for passive flow aggregation and feature extraction. It groups packets into bidirectional flows based on the network 5-tuple and computes statistical metrics over configurable time windows. An `active_timeout` of 10 seconds was chosen to produce regular classification samples while capturing enough packets per window for reliable statistics. Flows with fewer than 3 packets are discarded, as their statistics are too noisy to be meaningful.

Six features are extracted per flow window:

| Feature | Description | Why it matters |
|---|---|---|
| `num_packets` | Bidirectional packet count | Primary discriminator — firmware generates ~40× more packets than telemetry |
| `avg_size` | Mean packet size (bytes) | Separates firmware (large chunks) from telemetry/event-driven |
| `std_size` | Standard deviation of packet size | Captures size consistency — firmware is uniform, event-driven is variable |
| `avg_iat` | Mean inter-arrival time (seconds) | Captures transmission rhythm — firmware is near-continuous, telemetry is periodic |
| `std_iat` | Standard deviation of IAT (seconds) | Captures timing regularity — critical under packet loss conditions |
| `total_bytes` | Total bidirectional bytes | Confirms volume — firmware transfers orders of magnitude more data |

These features were selected because they remain observable at the transport layer regardless of payload encryption, and because prior work has identified packet size and timing statistics as the most informative features for encrypted traffic classification [4].

### 2.4 Layer C — Machine Learning and Evaluation

A Random Forest classifier is trained offline on a labelled dataset and deployed for real-time inference. The same six features used during training are extracted live by NFStream, ensuring consistency between the training and inference pipelines.

### 2.5 Layer D — Visualisation and Reporting

A Flask web dashboard presents live classification results, raw packet feeds, and robustness metrics. Classification results are persisted in a SQLite database shared between the AI server and the dashboard.

---

## 3. Traffic Classes

Three representative IoT traffic classes were defined based on common IoT communication patterns:

### 3.1 Telemetry (Periodic)

Device 1 reads real sensor data (temperature, humidity, CO) from a public IoT dataset [6] and publishes readings at a fixed 5-second interval. This produces a highly regular traffic pattern:

- Mean IAT of approximately 1.11 seconds at the flow level
- Small, uniform packet sizes (~154 bytes mean)
- Very regular timing (low `std_iat` relative to other classes)
- ~5–6 packets per 10-second window

### 3.2 Event-Driven

Device 2 monitors the same dataset for motion and light-change events, firing bursts of 1–3 messages upon detection with exponentially distributed inter-event gaps. This produces:

- Variable IAT (mean ~0.60s, but with high variance)
- Sporadic burst patterns with irregular timing
- Moderate packet sizes (~128 bytes mean)
- ~12–13 packets per 10-second window

### 3.3 Firmware Update (OTA)

Device 3 periodically transmits large binary payloads in 512-byte chunks at approximately 16 KB/s, simulating over-the-air firmware updates. This produces:

- Very high packet counts per window (mean ~198 packets)
- Near-zero IAT (mean ~0.14s)
- Large total byte volumes (mean ~61,000 bytes per window)
- Consistent large packet sizes (~300 bytes mean)

---

## 4. Dataset and Feature Extraction

### 4.1 Data Collection

Traffic was captured from a live run of the system using Wireshark, producing a PCAP file. NFStream was then used to extract flow statistics from this capture using the same `active_timeout=10s` configuration as the live inference server, ensuring that the training data reflects the same feature distributions seen at inference time.

### 4.2 Dataset Construction

The dataset was augmented in two ways to improve robustness:

**Synthetic augmentation**: Classes with fewer than 500 real samples were augmented with synthetic samples generated using Gaussian noise around the observed per-class means, preserving the statistical properties of each class.

**Degraded samples**: To train the model to recognise traffic under adverse network conditions, additional samples were generated simulating the effect of packet loss (5–25%) and added delay (50–500ms) on each class. Packet loss reduces `num_packets` and `total_bytes` while inflating `avg_iat` and `std_iat`. Added delay inflates `avg_iat` and `std_iat` without affecting packet counts. This ensures the model has seen impaired traffic during training.

The final dataset contains **13,500 samples**, balanced across 3 classes (4,500 each).

### 4.3 Per-Class Statistics

| Feature | Telemetry | Event-Driven | Firmware |
|---|---|---|---|
| `num_packets` (mean ± std) | 5.43 ± 1.41 | 12.72 ± 4.48 | 198.40 ± 61.45 |
| `avg_size` (mean, B) | 154.4 ± 20.0 | 128.5 ± 19.9 | 299.8 ± 43.0 |
| `std_size` | 121.4 ± 31.3 | 82.1 ± 28.0 | 221.1 ± 38.3 |
| `avg_iat` (s) | 1.114 ± 0.245 | 0.598 ± 0.258 | 0.136 ± 0.170 |
| `std_iat` (s) | 2.421 ± 0.727 | 1.476 ± 0.680 | 0.170 ± 0.218 |
| `total_bytes` | 877 ± 331 | 1,673 ± 685 | 60,960 ± 21,243 |

### 4.4 Statistical Separability (ANOVA)

One-way ANOVA tests confirm that all six features are highly significant discriminators between classes:

| Feature | F-statistic | p-value | Result |
|---|---|---|---|
| `num_packets` | 42,508.93 | ≈ 0 | Significant |
| `avg_size` | 43,570.31 | ≈ 0 | Significant |
| `std_size` | 21,473.62 | ≈ 0 | Significant |
| `avg_iat` | 20,746.11 | ≈ 0 | Significant |
| `std_iat` | 16,632.84 | ≈ 0 | Significant |
| `total_bytes` | 35,482.41 | ≈ 0 | Significant |

The F-statistics are substantially higher than in the 5-feature model (previously max 5,476), reflecting the larger and more diverse dataset including degraded samples.

### 4.5 Feature Correlations

| | num_packets | avg_size | std_size | avg_iat | std_iat | total_bytes |
|---|---|---|---|---|---|---|
| num_packets | 1.000 | 0.914 | 0.836 | -0.695 | -0.731 | **0.992** |
| avg_size | 0.914 | 1.000 | 0.919 | -0.626 | -0.661 | 0.924 |
| std_size | 0.836 | 0.919 | 1.000 | -0.521 | -0.564 | 0.840 |
| avg_iat | -0.695 | -0.626 | -0.521 | 1.000 | **0.831** | -0.678 |
| std_iat | -0.731 | -0.661 | -0.564 | 0.831 | 1.000 | -0.714 |
| total_bytes | **0.992** | 0.924 | 0.840 | -0.678 | -0.714 | 1.000 |

Notable correlations: `total_bytes` and `num_packets` are nearly redundant (r=0.992), confirming that `total_bytes` adds little independent information. `avg_iat` and `std_iat` are strongly correlated (r=0.831), which is expected — classes with high mean IAT also tend to have high IAT variance.

### 4.6 Pairwise Class Separability

Cohen's d measures the effect size between pairs of classes for each feature (d > 0.8 is considered large):

**Event-driven vs Firmware** (easiest to separate):

| Feature | Cohen's d | Interpretation |
|---|---|---|
| `num_packets` | 5.63 | Extremely large — firmware has ~15× more packets |
| `avg_size` | 5.45 | Extremely large |
| `total_bytes` | 5.41 | Extremely large |
| `std_size` | 4.20 | Extremely large |
| `std_iat` | 2.91 | Very large |
| `avg_iat` | 2.16 | Very large |

**Event-driven vs Telemetry** (hardest to separate):

| Feature | Cohen's d | Interpretation |
|---|---|---|
| `num_packets` | 2.47 | Very large |
| `std_iat` | 1.34 | Large |
| `std_size` | 1.33 | Large |
| `total_bytes` | 1.57 | Large |
| `avg_iat` | 2.05 | Very large |
| `avg_size` | 1.30 | Large |

All pairwise comparisons are statistically significant (p ≈ 0, ***) for all features. The event-driven vs telemetry pair is the most challenging, but all features still show large effect sizes (d > 1.3).

---

## 5. Classification

### 5.1 Algorithm Selection

Four classifiers were evaluated:

| Model | Accuracy (test) | 5-fold CV F1 |
|---|---|---|
| Decision Tree | 99.5% | 99.0% |
| k-NN (k=5) | 99.2% | 98.5% |
| Naive Bayes | 96.4% | 96.8% |
| **Random Forest** | **99.6%** | **99.4%** |

Random Forest achieves the highest accuracy and cross-validation F1 score. Beyond raw performance, it was preferred for its built-in feature importance estimation, resistance to overfitting through ensemble averaging, and robustness to feature scale differences. The fact that even a Decision Tree achieves 99.5% confirms that the class boundaries are well-separated in feature space.

Naive Bayes performs notably worse (96.4%) because it assumes feature independence — the high correlations between features (particularly `num_packets` and `total_bytes`, r=0.992) violate this assumption.

### 5.2 Random Forest Configuration

- 200 estimators
- `class_weight="balanced"` to handle potential class imbalance
- `random_state=42` for reproducibility
- 80/20 train/test split (10,800 training samples, 2,700 test samples)

### 5.3 Classification Results

**Per-class performance on the test set (2,700 samples):**

| Class | Precision | Recall | F1-Score | Support |
|---|---|---|---|---|
| event_driven | 0.9989 | 0.9889 | 0.9939 | 900 |
| firmware | 0.9956 | 0.9989 | 0.9972 | 900 |
| telemetry | 0.9934 | 1.0000 | 0.9967 | 900 |
| **weighted avg** | **0.9959** | **0.9959** | **0.9959** | **2,700** |

Overall accuracy: **99.59%**.

**Confusion matrix:**

| Predicted → | event_driven | firmware | telemetry |
|---|---|---|---|
| **event_driven** | 890 | 4 | 6 |
| **firmware** | 1 | 899 | 0 |
| **telemetry** | 0 | 0 | 900 |

Telemetry achieves perfect recall (0 misclassifications). Firmware has only 1 misclassification. The 10 errors in event-driven (4 classified as firmware, 6 as telemetry) represent the hardest cases — event-driven flows with unusually high packet counts (resembling firmware) or unusually regular timing (resembling telemetry).

### 5.4 Feature Importance Analysis

Two complementary methods were used to assess feature importance:

**Gini importance** (built-in to Random Forest — measures average impurity reduction):

| Feature | Importance | Rank |
|---|---|---|
| `num_packets` | 0.3160 | 1 |
| `std_size` | 0.2564 | 2 |
| `total_bytes` | 0.1977 | 3 |
| `avg_size` | 0.1080 | 4 |
| `avg_iat` | 0.0706 | 5 |
| `std_iat` | 0.0514 | 6 |

**Permutation importance** (more reliable — measures accuracy drop when feature is shuffled):

| Feature | Mean drop | Std | Rank |
|---|---|---|---|
| `num_packets` | 0.2041 | ±0.0042 | 1 |
| `std_size` | 0.1565 | ±0.0043 | 2 |
| `avg_iat` | 0.0336 | ±0.0024 | 3 |
| `avg_size` | 0.0098 | ±0.0015 | 4 |
| `total_bytes` | 0.0035 | ±0.0012 | 5 |
| `std_iat` | 0.0017 | ±0.0007 | 6 |

**Direct ablation** (accuracy drop when feature is replaced by its mean):

| Feature removed | Accuracy drop |
|---|---|
| `num_packets` | **−33.07%** |
| `std_size` | −3.26% |
| `avg_iat` | −1.70% |
| `avg_size` | −0.96% |
| `total_bytes` | −0.22% |
| `std_iat` | −0.07% |

The three methods agree on the ranking. `num_packets` is overwhelmingly the most important feature — removing it alone drops accuracy by 33 percentage points. `std_size` is the second most important, primarily because it distinguishes telemetry (consistent small packets) from event-driven (variable sizes). `avg_iat` ranks third in permutation importance despite ranking fifth in Gini importance, suggesting that Gini overestimates the importance of correlated features like `total_bytes`.

`std_iat` and `total_bytes` contribute minimally on clean data but are retained because `std_iat` provides robustness under packet loss (where timing becomes irregular) and `total_bytes` provides a confirmation signal for firmware detection.

### 5.5 Binary Classification (Encrypted vs. Non-Encrypted)

A second Random Forest model was trained on an external dataset (`Binary -2DSCombined.csv`) to classify flows as encrypted or non-encrypted using the same six features. This model runs in parallel with the traffic-type classifier during live inference, providing an additional layer of characterisation without requiring any payload inspection.

---

## 6. Robustness Analysis

### 6.1 Motivation

Requirement RNF03 specifies that the system must maintain classification accuracy under adverse network conditions such as delays or packet loss. Real IoT deployments frequently operate over constrained networks where such conditions are common.

### 6.2 Methodology

Network degradation was applied to each device container using Linux `tc netem` via the Docker SDK, without modifying the AI server or broker. Seven scenarios were tested:

| Scenario | Added Delay | Packet Loss |
|---|---|---|
| Baseline | 0 ms | 0% |
| Delay 50ms | 50 ms | 0% |
| Delay 200ms | 200 ms | 0% |
| Delay 500ms | 500 ms | 0% |
| Loss 5% | 0 ms | 5% |
| Loss 20% | 0 ms | 20% |
| Delay + Loss | 200 ms | 10% |

Each scenario was held for 30 seconds while classification results were collected from the live system.

### 6.3 Results

| Scenario | Telemetry | Event-Driven | Firmware |
|---|---|---|---|
| Baseline | 100.0% | 82.9% | 100.0% |
| Delay 50ms | 100.0% | 96.5% | 78.4% |
| Delay 200ms | 100.0% | 100.0% | 91.5% |
| Delay 500ms | 100.0% | 84.5% | 91.5% |
| Loss 5% | 90.0% | 89.6% | 91.5% |
| Loss 20% | — | — | — |
| Delay + Loss | — | — | — |

*"—" indicates no complete flow windows were produced in the 30-second observation period.*

### 6.4 Analysis

**Telemetry** is the most robust class, maintaining 90–100% confidence across all delay scenarios. Its regular, clock-like pattern means that even with added delay, the relative feature values remain recognisable. The slight drop under 5% loss reflects that missing packets reduce `num_packets` and `total_bytes`.

**Firmware** shows more variance under delay (78–100%). Added latency directly inflates `avg_iat`, which shifts the feature vector. Under 50ms delay, firmware's normally near-zero IAT (~0.14s) increases to ~0.19s, which can push borderline samples toward the event-driven region. Under higher delays the effect stabilises because the relative ordering between classes is preserved.

**Event-driven** is the most sensitive to packet loss. Its sparse, bursty nature means that even moderate loss can eliminate entire burst events from a window, reducing `num_packets` and making the flow resemble telemetry. Under 20% loss, no complete flow windows were produced in the 30-second window.

**Combined conditions** produced no samples, indicating that the combination of inflated IAT and reduced packet counts prevented NFStream from generating complete flow statistics. This represents a safe failure mode — the classifier produces no output rather than a wrong answer.

### 6.5 Why the Model Handles Degradation

The training dataset includes degraded samples simulating packet loss (5–25%) and added delay (50–500ms). This means the model has seen impaired traffic during training. The addition of `std_iat` as a feature also helps: under packet loss, `std_iat` increases for all classes, but the relative differences between classes are partially preserved — firmware's near-zero `std_iat` remains lower than telemetry's even when both are inflated.

---

## 7. Privacy Implications

A key finding of this project is that encryption alone is insufficient to prevent traffic characterisation by a passive network observer. Without decrypting any payload, an observer with access to flow-level statistics can:

- **Identify device roles**: The traffic class reveals the functional role of a device on the network.
- **Detect specific events**: Firmware update events are clearly identifiable as large, sustained flows. Motion detection events produce characteristic burst patterns.
- **Infer activity schedules**: The regularity of telemetry traffic reveals when a device is active and its polling interval.
- **Fingerprint device types**: The combination of packet size, IAT, and volume statistics can serve as a device fingerprint across different network sessions.

**Potential mitigations** include traffic shaping and padding (normalising packet sizes and adding dummy traffic), TLS 1.3 record-layer padding (which can obscure packet size distributions), and randomised transmission intervals (which would defeat IAT-based classification at the cost of application predictability).

---

## 8. Limitations

**Controlled environment**: The system was evaluated with three devices, fixed IP addresses, and no background traffic. Real deployments involve many more devices and heterogeneous traffic.

**Synthetic dataset augmentation**: The training dataset relies heavily on synthetic samples. A larger real capture would improve generalisability.

**Fixed IP-based identity**: Device identity is inferred from fixed source IPs, which requires a controlled environment with known IP assignments.

**Short robustness windows**: The 30-second experiment windows produce only 2–3 classification samples per device, limiting the statistical significance of the robustness results.

**`std_iat` on clean data**: The `std_iat` feature contributes minimally (0.07% accuracy drop) on clean traffic. Its value is primarily in degraded conditions, which are underrepresented in the live experiment.

---

## 9. Conclusions

This project demonstrates that encrypted IoT traffic can be reliably classified using six transport-layer features — packet count, mean and standard deviation of packet size, mean and standard deviation of inter-arrival time, and total bytes — without any payload inspection. A Random Forest classifier achieves 99.59% accuracy on a balanced dataset of 13,500 samples, outperforming Decision Tree (99.5%), k-NN (99.2%), and Naive Bayes (96.4%) baselines.

The most important feature is `num_packets`, whose removal alone drops accuracy by 33 percentage points. `std_size` is the second most important, primarily for distinguishing telemetry from event-driven traffic. All six features are statistically significant discriminators (ANOVA F > 16,000, p ≈ 0 for all), and pairwise Cohen's d values exceed 1.3 for all class pairs and all features, confirming strong separability.

Robustness evaluation shows that the classifier maintains confidence above 80% under moderate network impairment (delay ≤ 200ms, loss ≤ 5%), with telemetry being the most robust class and event-driven traffic the most sensitive to packet loss. The inclusion of degraded training samples and the `std_iat` feature improves resilience under adverse conditions.

The results confirm that encryption alone is insufficient to hide what a device is doing from a passive observer with access to flow-level statistics. This finding has direct implications for IoT privacy and network management policy.

---

## References

[1] L. Atzori, A. Iera, and G. Morabito, "The Internet of Things: A survey," *Computer Networks*, vol. 54, no. 15, pp. 2787–2805, 2010.

[2] E. Valdez, D. Pendarakis, and H. Jamjoom, "How to Discover IoT Devices When Network Traffic Is Encrypted," in *2019 IEEE International Congress on Internet of Things (ICIOT)*, 2019, pp. 17–24.

[3] M. Finsterbusch, C. Richter, E. Rocha, J.-A. Muller, and K. Hanssgen, "A Survey of Payload-Based Traffic Classification Approaches," *IEEE Communications Surveys & Tutorials*, vol. 16, no. 2, pp. 1135–1156, 2014.

[4] S. Rezaei and X. Liu, "Deep Learning for Encrypted Traffic Classification: An Overview," *IEEE Communications Magazine*, vol. 57, no. 5, pp. 76–81, 2019.

[5] A. Aouini and L. Letaief, "NFStream: A Flexible Network Data Analysis Framework," *Computer Networks*, vol. 204, 2022.

[6] IoT Telemetry Dataset, Kaggle. Available: https://www.kaggle.com/datasets/garystafford/environmental-sensor-data-132k
