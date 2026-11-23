// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IFreelinkEscrowAccept {
    function acceptEscrow(bytes32 escrowId, bytes32 termsHash, uint256 expectedAmount, uint64 expectedDeadline) external;
}

/// @dev ใช้ในเทสต์เท่านั้น: freelancer ที่เป็น contract แล้วตอบกลับข้อมูล (returndata) ก้อนใหญ่ที่สุดเท่าที่ gas พอ
///      ถ้าผู้จ่ายเงิน copy returndata กลับมา ผู้จ่ายจะต้องเสีย gas ค่า memory จนหมด แล้วทั้งธุรกรรมล้ม
///      (returndata bomb) ซึ่งทำให้ freelancer ขวางคำตัดสินแบบแบ่งเงินและการแบ่งครึ่งตอนหมดเวลาได้
contract ReturnBombMock {
    IFreelinkEscrowAccept public immutable escrow;

    constructor(address escrow_) {
        escrow = IFreelinkEscrowAccept(escrow_);
    }

    function accept(bytes32 escrowId, bytes32 termsHash, uint256 amount, uint64 deadline) external {
        escrow.acceptEscrow(escrowId, termsHash, amount, deadline);
    }

    receive() external payable {
        // ค่า memory ของ w words ประมาณ 3w + w²/512 เลือก w ให้ใช้ราว 80% ของ gas ที่ได้รับมา
        // ผู้จ่ายที่ copy returndata ต้องจ่ายค่า memory เท่ากันจาก gas ที่เหลือแค่ 1/64 จึงไม่พอ
        uint256 words = (_sqrt(512 * gasleft()) * 9) / 10;
        assembly {
            return(0, mul(words, 32))
        }
    }

    function _sqrt(uint256 x) private pure returns (uint256 y) {
        if (x == 0) return 0;
        uint256 z = (x + 1) / 2;
        y = x;
        while (z < y) {
            y = z;
            z = (x / z + z) / 2;
        }
    }
}
