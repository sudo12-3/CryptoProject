
# Centralized UPI Payment Gateway with Quantum Security Analysis

## Project Overview
The system implements a centralized UPI payment gateway with the following key features:
- Real-time transaction processing using SpeckCipher for lightweight cryptography
- Quantum vulnerability analysis using Shor's Algorithm simulation
- Multi-layer authentication (PIN, biometric) for enhanced security
- Merchant identity protection using MID to VID encryption
- Transaction verification and logging using blockchain

## System Architecture

├── Bank/               # Bank server and API implementation
├── Merchant/           # Merchant registration and management
├── UPI_Machine/        # Transaction processing and verification
├── User/               # User authentication and interface
├── quantum_crypto.py   # Quantum vulnerability demonstration
└── lwc.py             # Lightweight cryptography implementation


## Key Features

### 1. User Management
- Secure registration with MMID (Mobile Money Identifier) generation
- PIN and biometric authentication
- Transaction history tracking
- Balance management and verification

### 2. Merchant Services
- Secure merchant registration
- MID (Merchant ID) to VID (Virtual ID) encryption
- QR code generation for payments
- Transaction history and balance tracking

### 3. Security Implementation
- SpeckCipher for lightweight encryption
- SHA-256 hashing for data integrity
- Blockchain for transaction verification
- Quantum attack simulation using Shor's Algorithm

### 4. Transaction Flow
1. User initiates payment using merchant's VID
2. UPI Machine verifies user credentials
3. Bank processes transaction and updates blockchain
4. Merchant receives payment confirmation

## Setup Instructions

1. *Install Dependencies*
bash
pip install -r requirements.txt


2. *Configure Environment*
- Create serviceAccountKey.json for Firebase
- Set up environment variables

3. *Run Components*
bash
# Start Bank Server
python main.py

# Launch UPI Machine
python UPI_Machine/upi_machine_server.py

# Run User Interface
python main.py


4. *Test Quantum Analysis*
bash
python quantum_crypto.py


## Quantum Cryptography Note
The Shor's Algorithm implementation demonstrates how quantum computers could potentially break the classical encryption methods used in current payment systems. This is implemented as a separate module to simulate the vulnerability without affecting the main transaction flow.

## Testing
Run the test suite:
bash
pytest tests/


## Team Members
1. Sriharish Ravichandran - 2022A7PS0511H
2. Parth Mehta - 2022A7PS0043H
3. Anand Srinivasan - 2022A7PS2017H
4. Sagar Thomas - 2022A7PS0156H

## Requirements
- Python 3.8+
- Firebase Admin SDK
- Qiskit (for quantum simulation)
- PyTest (for testing)

## License
This project is licensed under the MIT License - see the LICENSE file for details.
