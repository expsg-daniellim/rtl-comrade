// vim: set ts=2 sw=2 et :
//
// Expedera R&D Pte Ltd Confidential 2024
//
// Lightwieght Verification Methodology (LVM)
//
// Reporting Macros for use by RTL designs
// When synthesizing design SYNTHESIS verilog define should be set
// this will replace calls to lvm reporter with verilog system tasks instead
// 
`ifndef LVM_RPT__SV
`define LVM_RPT__SV

`ifndef SYNTHESIS

typedef class GlobalLvmTestCore;

`define lvm_get_singleton \
  GlobalLvmTestCore::get_singleton()

`define lvm_dut_rpt_inf(fmt_msg) \
  `lvm_get_singleton.rpt_inf($sformatf fmt_msg)

`define lvm_dut_rpt_wrn(fmt_msg) \
  `lvm_get_singleton.rpt_wrn($sformatf fmt_msg)

`define lvm_dut_rpt_err(fmt_msg) \
  `lvm_get_singleton.rpt_err($sformatf fmt_msg)

`define lvm_dut_rpt_fat(fmt_msg) \
  `lvm_get_singleton.rpt_fat($sformatf fmt_msg)

`else //SYNTHESIS

// following versions are used with synthesis tools

`define lvm_dut_rpt_inf(fmt_msg) \
  $display($sformatf fmt_msg)

`define lvm_dut_rpt_wrn(fmt_msg) \
  $warning($sformatf fmt_msg)

`define lvm_dut_rpt_err(fmt_msg) \
  $error($sformatf fmt_msg)

`define lvm_dut_rpt_fat(fmt_msg) \
  $fatal($sformatf fmt_msg)

`endif//SYNTHESIS

`endif//LVM_RPT__SV
