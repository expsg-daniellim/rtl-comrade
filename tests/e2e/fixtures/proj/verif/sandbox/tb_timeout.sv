// vim: set ts=2 sw=2 et :
//
// Sim-timeout fixture for spec 12 sim-timeout parity. Drives a free-running
// clock and never calls $finish, so the simulation runs until the per-test
// `sim_timeout` wall-clock limit kills it (run-process rc -> None -> the
// SimTimeout verdict). Paired with the `sim_timeout` test in tests.yaml.
module tb_timeout;

  localparam W = 4;

  logic clk;
  logic rst;
  logic[W-1:0] a;
  logic[W-1:0] b;
  logic[W-1:0] z;

  // DUT from the `test_module` model (design/sandbox/test_module.sv)
  test_module #(.WIDTH(W)) i_dut( .clk, .rst, .a, .b, .z );

  initial begin
    clk = '0;
    rst = '1;
    a   = '0;
    b   = '0;
    $display("tb_timeout: starting, intentionally never $finish");
    repeat (4) @(negedge clk);
    rst = '0;
    // spin forever: no $finish, rely on the harness sim_timeout to kill it
    forever begin
      @(negedge clk);
      a = a + 1;
      b = b + 1;
    end
  end

  always #500ps clk = ~clk;

endmodule
