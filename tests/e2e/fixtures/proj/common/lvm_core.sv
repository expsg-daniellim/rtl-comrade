// vim: set ts=2 sw=2 et :
//
// Expedera R&D Pte Ltd Confidential 2024
//
// Lightwieght Verification Methodology (LVM)
// 

`timescale 1ns/10ps

typedef class GlobalLvmTestCore;

package LvmPkg;

typedef class TestCore;

// LVM MACROS

`define LVM_INIT_CUSTOM(testname, local_class_name) \
  local_class_name tc; \
  initial begin:tc_init \
    tc = new(testname); \
  end:tc_init \
  final begin:tc_final \
    tc.end_of_test(); \
  end:tc_final \
  `ifdef DUMP \
  initial begin:tc_dump \
  `ifdef VCS \
    $vcdpluson; \
    $vcdplusmemon; \
  `endif \
  `ifdef VERILATOR \
      $dumpfile("dump.fst"); \
      $dumpvars(); \
  `endif \
  end:tc_dump \
  `endif \

 
// Top-level testbench should call `LVM_INIT(testname)
// at the beginning of the module
`define LVM_INIT(testname) \
  `LVM_INIT_CUSTOM(testname,LvmPkg::TestCore)

// Error Reporting Macros
`define lvm_rpt_inf(fmt_msg) \
  tc.rpt_inf($sformatf fmt_msg)
`define lvm_rpt_wrn(fmt_msg) \
  tc.rpt_wrn($sformatf fmt_msg)
`define lvm_rpt_err(fmt_msg) \
  tc.rpt_err($sformatf fmt_msg)
`define lvm_rpt_fat(fmt_msg) \
  tc.rpt_fat($sformatf fmt_msg)

// Interface
interface class TestEndHook;
  pure virtual function void end_of_test(LvmPkg::TestCore c);
endclass

// Empty EndHook
class NullEndHook implements TestEndHook;
  virtual function void end_of_test(LvmPkg::TestCore c);
  endfunction
endclass

// TestCore
// Core framework for handling test reporting
class TestCore;

  string name;

  local TestEndHook end_hooks[$];

  const integer RPT_INF = 0;
  const integer RPT_WRN = 1;
  const integer RPT_ERR = 2;
  const integer RPT_FAT = 3;

  integer verbosity = RPT_ERR;

  integer ninf = 0;
  integer nerr = 0;
  integer nwrn = 0;
  integer nfat = 0;

  function new(string new_name);
    $display("TestCore(%s) new", new_name);
    this.name = new_name;
    if ($test$plusargs("lvm_verbosity"))
      begin
      $value$plusargs("lvm_verbosity=%d", this.verbosity);
      $display("set lvm_verbosity=%1d", this.verbosity);
      end
    TestCore::singleton = this;
  endfunction

  function void add_test_end_hook(TestEndHook h);
    this.end_hooks.push_back(h);
  endfunction

  // TODO randseed

  static local TestCore singleton;

  static function TestCore get_singleton();
    return TestCore::singleton;
  endfunction
  
  // report information 
  function void rpt_inf(string s);
    ninf++;
    if (this.verbosity <= RPT_INF)
      $display("INF: %t %s", $time, s);
  endfunction

  // report warnings 
  function void rpt_wrn(string s);
    nwrn++;
    if (this.verbosity <= RPT_WRN)
      $display("WRN: %t %s", $time, s);
  endfunction

  // report errors 
  function void rpt_err(string s);
    nerr++;
    if (this.verbosity <= RPT_ERR)
      $display("ERR: %t %s", $time, s);
  endfunction

  // report fatals 
  function void rpt_fat(string s);
    nfat++;
    if (this.verbosity <= RPT_FAT) begin
      $display("FAT: %t %s", $time, s);
    end
    end_of_test();
    $fatal(0);
  endfunction

  // end of test cleanup
  // this is registered with final begin/end in the LVM_INIT macro
  //breaking up the final report printing to make it easier to override in local extensions
  virtual function void report_preface();
    $display("Test Complete");
    $display("-------------------------");
    $display("name : %s", name);
    $display("-------------------------");
    foreach(this.end_hooks[i])
      end_hooks[i].end_of_test(this);
    $display("-------------------------");
  endfunction

  virtual function void report_values();
    $display("info : %4d", ninf);
    $display("warn : %4d", nwrn);
    $display("error: %4d", nerr);
    $display("fatal: %4d", nfat);
  endfunction

  virtual function void report_result();
    $display("-------------------------");
    $display();
    if (nerr + nfat > 0)
      $display("FAIL (nerr=%3d, nfat=%3d)", nerr, nfat);
    else
      $display("PASS (nwrn=%3d)", nwrn);
  endfunction

  function void end_of_test();
    report_preface();
    report_values();
    foreach(this.end_hooks[i])
      end_hooks[i].end_of_test(this);
    report_result();
  endfunction

endclass


// LvmComponent class
// For testbench components to extend
class LvmComponent;

  TestCore tc; // handle to the TestCore in tb_top

  function new(TestCore etc);
    this.tc = etc;
  endfunction

  function void rpt_inf(string s);
    tc.rpt_inf(s);
  endfunction
  
  function void rpt_wrn(string s);
    tc.rpt_inf(s);
  endfunction

  function void rpt_err(string s);
    tc.rpt_inf(s);
  endfunction

  function void rpt_fat(string s);
    tc.rpt_inf(s);
  endfunction

endclass

endpackage // LvmPkg

class GlobalLvmTestCore;

  static local LvmPkg::TestCore singleton;

  static function LvmPkg::TestCore get_singleton();
    if (singleton==null)
      GlobalLvmTestCore::singleton = LvmPkg::TestCore::get_singleton();
    return GlobalLvmTestCore::singleton;
  endfunction

endclass
