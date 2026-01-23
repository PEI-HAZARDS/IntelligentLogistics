# Intelligent Logistics  

[![Figma](https://img.shields.io/badge/Figma-Design-orange?logo=figma)](https://www.figma.com/files/team/1309815608365821624/project/171687163/PEI?fuid=1309815603742744973)
[![Microsite](https://img.shields.io/badge/Microsite-PEI-blue?logo=github)](https://pei-hazards.github.io/Micro-site/)


## Introduction  
We live in an era where logistics is invisible but essential: our orders arrive the next day with just a click, but behind this process there are millions of containers and complex operations. In 2023 alone, it is estimated that **858 million containers** passed through seaports worldwide, moved by ships, trucks, and land infrastructure.  

This growing volume brings with it huge logistical challenges: delays, routing errors, and operational costs. In large ports — veritable mazes with dozens of warehouses — a single wrong instruction is enough for cargo to be sent to the wrong destination, generating **losses of time and money**.  

---

## Motivation  
To increase **efficiency** and reduce costs, port authorities are adopting **Information and Communication Technologies (ICT)** and **Industry 4.0** concepts. With the democratization of **Artificial Intelligence**, **cloud computing**, and the **digitization of processes**, innovative solutions are emerging to make logistics more **intelligent, automated, and sustainable**.  

The **Intelligent Logistics** project proposes exactly that:  
- Automate the **truck entry control** in a port.  
- Detect vehicles and cargo using cameras and computer vision algorithms.  
- Integrate the information with an **intelligent logistics system** that decides the correct entry and destination.  
- Clearly inform the driver, whether through **digital signage** at the port or **mobile applications**.  

---

## System Design  
The system is based on two main modules:  

1. **Cargo Detection and Routing**  
   - Use of real-time computer vision algorithms (e.g., YOLO).  
   - Recognition of trucks, license plates, and dangerous goods symbols.  
   - Automatic routing to the correct destination within the port.  

2. **Statistical Analysis**  
   - Accounting of vehicles, cargo types, and dwell times.  
   - Visualization of metrics in different granularities (daily, monthly, individual).  

---

## Requirements  

### **Functional**  
- Automatic detection of trucks in real-time.  
- Detection and classification of license plates.
- Detection and classification of dangerous goods symbols.
- Identification of dangerous cargo through the safety placard.
- Vehicle state management.
- Integration with logistics management system for decision making.  
- Routing of the vehicle to the correct destination within the port.  
- Clear notification to the driver (via digital signage or mobile application).  
- Generation of statistical reports on traffic and cargo.

### **Non-Functional**  
- **Energy efficiency**: optimization of computational resource usage.  
- **Scalability**: allow adaptation to different ports and scenarios.
- **Flexibility**: active learning of new symbols/cargo types (?).  
- **Reliability**: robust system with low error rate.
- **Security**: protection of logistics data and monitored vehicles.
- Response time: Detection and notification must not exceed 2 seconds between capture and availability to the operator.
- Reliability: The system must maintain a minimum availability of 99% in the production environment.

---

## Future Evolutions (Phase II)  
- **Active learning**: allow the system to learn to identify new cargo types and symbols as they arise.  
- **Energy efficiency**: optimize the use of AI resources in datacenters, balancing performance and energy consumption.  

---

## Demonstration  
There is the possibility of integration with **real datacenters** and operating networks, as well as conducting practical tests in a port environment (such as the Port of Aveiro).  

---

✨ This project combines **AI, computer vision, logistics, and energy efficiency**, being a proposal aligned with the challenges of Industry 4.0.  


## Future Work

- Administration interface.
- Interaction via dashboard between the gate operator and driver (?).
- Monitoring
