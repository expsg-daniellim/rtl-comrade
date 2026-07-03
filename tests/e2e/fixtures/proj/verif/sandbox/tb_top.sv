// vim: set ts=2 sw=2 et :
//
// Expedera R&D Pte Ltd Confidential 2024
//
// lvm_core contains Lightweight Verification Methodolgy 
// core test framework, report handling, error counting, pass/fail
`include "lvm_core.sv"

// Any end_of_test code should be called via the EndHook class interface
//
// See this example on how to use EndHooks to 
// implement end_of_test notifications
class EndHook implements LvmPkg::TestEndHook;
  virtual function void end_of_test(LvmPkg::TestCore c);
    begin
    $display("custom end_of_test()");
    $display("nerr=%d", c.nerr);
    $display("tb_top.a = %d", tb_top.a);
    if (tb_top.a < 8)
      tb_top.`lvm_rpt_err(("random error injected, a=%d", tb_top.a));
    end
  endfunction
endclass

module tb_top;

  // register this module as the test top-level, test name is 
  // the first arg to LVM_INIT()
  `LVM_INIT("sandbox_test")

  logic clk;
  logic rst;

  localparam W = 4;
  logic[W-1:0] a;
  logic[W-1:0] b;
  logic[W-1:0] z;
  logic[W-1:0] u;
  integer test_cycles = 20;

  typedef struct packed {
    logic[3:0] b;
    logic[3:0] a;
  } struct_test_t;

  //test_module #(.WIDTH(W)) i_dut( .clk, .rst, .a, .b, .z );

  test_mem_if #(.WIDTH(W)) i_mem_if();

  //test_module_2 #() i_dut_2( .clk, .rst, .m(i_mem_if), .z);
  test_module_3 #(.WIDTH(W)) i_dut_2( .clk, .rst, .m(i_mem_if), .z);

  prog_mon #(.W(W)) i_prog_mon( .clk, .rst, .a, .b, .z, .u );

  //end-of-test hook
  EndHook eh;

  initial begin
  struct_test_t s;
  eh = new();
  tc.add_test_end_hook(eh);
  
  clk = '0;
  rst = '1;
  a   = '0;
  b   = '0;
  u   = 'x;

  `lvm_rpt_inf(("test starting"));

  if ($test$plusargs("a")) begin
  $value$plusargs("a=%d", a);
  $display("plusargs set a=%d", a);
  end
  if ($test$plusargs("b")) begin
  $value$plusargs("b=%d", b);
  $display("plusargs set b=%d", b);
  end
  if ($test$plusargs("flag")) begin 
  $display("plusargs set flag");
  end
  if ($test$plusargs("test_cycles")) begin
  $value$plusargs("test_cycles=%d", test_cycles);
  end
  repeat (4) @(negedge clk);
  `lvm_rpt_inf(("reset deasserted"));
  rst = '0;
  repeat (test_cycles) begin
    `lvm_rpt_inf(("b=%d", b));
    b = b + 1;
    @(negedge clk);
  end

  s = 8'h21;
  $display("struct test %x s.a=%h s.b=%h", s, s.a, s.b);

  $finish(0);
  end

  assign i_mem_if.a = a;
  assign i_mem_if.b = b;


  initial begin
`ifdef TRACE
    $display("+define+TRACE detected");
`endif
`ifdef DEFINE_WO_VALUE
    $display("DEFINE_WO_VALUE");
`endif
`ifdef DEFINE_WITH_VALUE
    $display("DEFINE_WITH_VALUE = %d", `DEFINE_WITH_VALUE);
`endif
  end

  // DO NOT USE final begin end in tb_top module
  // use the TestHook methodology instead to ensure
  // that your cleanup tasks are done before the final PASS/FAIL
  // message is produced for the regression infrastructure
  //
  // final begin
  //   if (a<8)
  //     $display("PASS - random pass");
  //   else
  //     $display("FAIL - random fail");
  // end


  always #500ps clk = ~clk;

endmodule

program prog_mon#(parameter W)(
    input clk,
    input rst,
    input[W-1:0] a,
    input[W-1:0] b,
    input[W-1:0] z,
    input[W-1:0] u
  );

  initial begin
    while(1) begin
      @(posedge clk);
      //$display("%t a=%x b=%x z=%x u=%x", $time, a, b, z, u);
      tb_top.`lvm_rpt_inf(("a=%x b=%x z=%x u=%x", a, b, z, u));
      end
  end

endprogram
