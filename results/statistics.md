# Statistical test results (mean±std / 95%CI / paired Wilcoxon)

> α = 0.05, two-tailed; 95%CI uses the t distribution; Wilcoxon is paired by trial. n<3 is recorded as N/A; strategies with isomorphic outputs (all-zero differences) are recorded as tied (p=1.0, not testable).


## E1 — statistics

### (conflict = ('high',))
| strategy | tau_causal | tau_contested | tauhat | info_retention |
|---|---|---|---|---|
| crdt_lww | 16.200±14.108 (8.387,24.013) n=15 | 711.600±112.222 (649.454,773.746) n=15 | 0.315±0.051 (0.287,0.343) n=15 | 0.685±0.051 (0.657,0.713) n=15 |
| crdt_pure | 0.000±0.000 (n=15) | 627.200±66.099 (590.596,663.804) n=15 | 0.271±0.027 (0.257,0.286) n=15 | 0.729±0.027 (0.714,0.743) n=15 |
| leader | 2.733±4.044 (0.494,4.973) n=15 | 119.267±75.425 (77.498,161.036) n=15 | 0.053±0.033 (0.035,0.071) n=15 | 0.947±0.033 (0.929,0.965) n=15 |
| lww | 16.200±14.108 (8.387,24.013) n=15 | 711.600±112.222 (649.454,773.746) n=15 | 0.315±0.051 (0.287,0.343) n=15 | 0.685±0.051 (0.657,0.713) n=15 |
| ranked_pairs | 0.000±0.000 (n=15) | 522.533±61.690 (488.370,556.696) n=15 | 0.226±0.023 (0.213,0.239) n=15 | 0.774±0.023 (0.761,0.787) n=15 |
| vc | 0.000±0.000 (n=15) | 831.867±95.794 (778.818,884.916) n=15 | 0.360±0.042 (0.337,0.384) n=15 | 0.640±0.042 (0.616,0.663) n=15 |

> Significant differences (p<0.05): crdt_lww vs crdt_pure (p=0.0001); crdt_lww vs leader (p=0.0001); crdt_lww vs ranked_pairs (p=0.0001); crdt_lww vs vc (p=0.0151); crdt_pure vs leader (p=0.0001); crdt_pure vs lww (p=0.0001); crdt_pure vs ranked_pairs (p=0.0001); crdt_pure vs vc (p=0.0001); leader vs lww (p=0.0001); leader vs ranked_pairs (p=0.0001); leader vs vc (p=0.0001); lww vs ranked_pairs (p=0.0001); lww vs vc (p=0.0151); ranked_pairs vs vc (p=0.0001); Isomorphic (indistinguishable): crdt_lww ≡ lww

### (conflict = ('low',))
| strategy | tau_causal | tau_contested | tauhat | info_retention |
|---|---|---|---|---|
| crdt_lww | 55.333±31.726 (37.764,72.902) n=15 | 588.600±164.077 (497.737,679.463) n=15 | 0.283±0.081 (0.238,0.328) n=15 | 0.717±0.081 (0.672,0.762) n=15 |
| crdt_pure | 0.000±0.000 (n=15) | 444.267±60.827 (410.582,477.952) n=15 | 0.196±0.026 (0.181,0.210) n=15 | 0.804±0.026 (0.790,0.819) n=15 |
| leader | 8.267±11.241 (2.042,14.492) n=15 | 272.467±80.758 (227.744,317.189) n=15 | 0.124±0.038 (0.103,0.145) n=15 | 0.876±0.038 (0.855,0.897) n=15 |
| lww | 55.333±31.726 (37.764,72.902) n=15 | 588.600±164.077 (497.737,679.463) n=15 | 0.283±0.081 (0.238,0.328) n=15 | 0.717±0.081 (0.672,0.762) n=15 |
| ranked_pairs | 0.000±0.000 (n=15) | 365.467±44.989 (340.553,390.381) n=15 | 0.161±0.019 (0.151,0.171) n=15 | 0.839±0.019 (0.829,0.849) n=15 |
| vc | 0.000±0.000 (n=15) | 539.400±96.612 (485.898,592.902) n=15 | 0.238±0.042 (0.214,0.261) n=15 | 0.762±0.042 (0.739,0.786) n=15 |

> Significant differences (p<0.05): crdt_lww vs crdt_pure (p=0.0001); crdt_lww vs leader (p=0.0001); crdt_lww vs ranked_pairs (p=0.0001); crdt_pure vs leader (p=0.0003); crdt_pure vs lww (p=0.0001); crdt_pure vs ranked_pairs (p=0.0001); crdt_pure vs vc (p=0.0026); leader vs lww (p=0.0001); leader vs ranked_pairs (p=0.0067); leader vs vc (p=0.0001); lww vs ranked_pairs (p=0.0001); ranked_pairs vs vc (p=0.0001); Isomorphic (indistinguishable): crdt_lww ≡ lww

## E2 — statistics

###

| strategy | ops_retained | auto_coverage | info_retention | tau_causal | tau_contested | semantic_validity | gini | time_ms |
|---|---|---|---|---|---|---|---|---|
| crdt_lww | 1.000±0.000 (n=15) | 1.000±0.000 (n=15) | 0.675±0.037 (0.654,0.695) n=15 | 14.400±9.657 (9.052,19.748) n=15 | 717.333±82.280 (671.768,762.898) n=15 | 0.749±0.296 (0.585,0.913) n=15 | 0.109±0.029 (0.093,0.125) n=15 | 0.012±0.000 (0.012,0.013) n=15 |
| crdt_pure | 1.000±0.000 (n=15) | 0.592±0.124 (0.523,0.660) n=15 | 0.723±0.033 (0.705,0.742) n=15 | 0.000±0.000 (n=15) | 621.400±65.539 (585.106,657.694) n=15 | 0.728±0.322 (0.550,0.907) n=15 | 0.131±0.025 (0.117,0.145) n=15 | 0.023±0.002 (0.022,0.025) n=15 |
| leader | 0.350±0.044 (0.326,0.374) n=15 | 1.000±0.000 (n=15) | 0.966±0.014 (0.958,0.974) n=15 | 1.000±2.646 (-0.465,2.465) n=15 | 76.400±31.593 (58.904,93.896) n=15 | 1.000±0.000 (n=15) | 0.291±0.039 (0.270,0.313) n=15 | 0.007±0.000 (0.007,0.007) n=15 |
| lww | 1.000±0.000 (n=15) | 1.000±0.000 (n=15) | 0.675±0.037 (0.654,0.695) n=15 | 14.400±9.657 (9.052,19.748) n=15 | 717.333±82.280 (671.768,762.898) n=15 | 0.749±0.296 (0.585,0.913) n=15 | 0.109±0.029 (0.093,0.125) n=15 | 0.014±0.003 (0.012,0.016) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 1.000±0.000 (n=15) | 0.768±0.027 (0.753,0.783) n=15 | 0.000±0.000 (n=15) | 520.333±50.037 (492.624,548.043) n=15 | 0.870±0.197 (0.761,0.979) n=15 | 0.170±0.032 (0.152,0.188) n=15 | 0.801±0.076 (0.758,0.843) n=15 |
| vc | 1.000±0.000 (n=15) | 0.592±0.124 (0.523,0.660) n=15 | 0.613±0.051 (0.585,0.641) n=15 | 0.000±0.000 (n=15) | 868.200±100.464 (812.565,923.835) n=15 | 0.779±0.301 (0.612,0.945) n=15 | 0.107±0.032 (0.090,0.125) n=15 | 0.046±0.003 (0.044,0.048) n=15 |

> Significant differences (p<0.05): crdt_lww vs crdt_pure (p=0.0001); crdt_lww vs leader (p=0.0001); crdt_lww vs ranked_pairs (p=0.0001); crdt_lww vs vc (p=0.0006); crdt_pure vs leader (p=0.0001); crdt_pure vs lww (p=0.0001); crdt_pure vs ranked_pairs (p=0.0001); crdt_pure vs vc (p=0.0001); leader vs lww (p=0.0001); leader vs ranked_pairs (p=0.0001); leader vs vc (p=0.0001); lww vs ranked_pairs (p=0.0001); lww vs vc (p=0.0006); ranked_pairs vs vc (p=0.0001); Isomorphic (indistinguishable): crdt_lww ≡ lww

## E6a — statistics

### (minority_frac = (0.1,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.900±0.072 (0.860,0.940) n=15 | 0.743±0.049 (0.716,0.770) n=15 | 0.257±0.049 (0.230,0.284) n=15 |
| lww | 1.000±0.000 (n=15) | 0.675±0.055 (0.645,0.705) n=15 | 0.325±0.055 (0.295,0.355) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 0.775±0.026 (0.761,0.789) n=15 | 0.225±0.026 (0.211,0.239) n=15 |

> Significant differences (p<0.05): leader vs lww (p=0.0006); lww vs ranked_pairs (p=0.0001)

### (minority_frac = (0.2,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.792±0.057 (0.760,0.823) n=15 | 0.800±0.041 (0.777,0.822) n=15 | 0.200±0.041 (0.178,0.223) n=15 |
| lww | 1.000±0.000 (n=15) | 0.678±0.037 (0.657,0.699) n=15 | 0.322±0.037 (0.301,0.343) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 0.773±0.021 (0.761,0.784) n=15 | 0.227±0.021 (0.216,0.239) n=15 |

> Significant differences (p<0.05): leader vs lww (p=0.0001); lww vs ranked_pairs (p=0.0001)

### (minority_frac = (0.3,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.689±0.105 (0.630,0.747) n=15 | 0.846±0.047 (0.820,0.871) n=15 | 0.154±0.047 (0.129,0.180) n=15 |
| lww | 1.000±0.000 (n=15) | 0.696±0.036 (0.677,0.716) n=15 | 0.304±0.036 (0.284,0.323) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 0.780±0.031 (0.763,0.797) n=15 | 0.220±0.031 (0.203,0.237) n=15 |

> Significant differences (p<0.05): leader vs lww (p=0.0001); leader vs ranked_pairs (p=0.0004); lww vs ranked_pairs (p=0.0001)

### (minority_frac = (0.4,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.581±0.118 (0.515,0.646) n=15 | 0.900±0.036 (0.880,0.920) n=15 | 0.100±0.036 (0.080,0.120) n=15 |
| lww | 1.000±0.000 (n=15) | 0.693±0.044 (0.669,0.718) n=15 | 0.307±0.044 (0.282,0.331) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 0.779±0.016 (0.770,0.788) n=15 | 0.221±0.016 (0.212,0.230) n=15 |

> Significant differences (p<0.05): leader vs lww (p=0.0001); leader vs ranked_pairs (p=0.0001); lww vs ranked_pairs (p=0.0001)

### (minority_frac = (0.5,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.508±0.095 (0.456,0.561) n=15 | 0.916±0.038 (0.895,0.937) n=15 | 0.084±0.038 (0.063,0.105) n=15 |
| lww | 1.000±0.000 (n=15) | 0.690±0.035 (0.671,0.709) n=15 | 0.310±0.035 (0.291,0.329) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 0.777±0.018 (0.767,0.787) n=15 | 0.223±0.018 (0.213,0.233) n=15 |

> Significant differences (p<0.05): leader vs lww (p=0.0001); leader vs ranked_pairs (p=0.0001); lww vs ranked_pairs (p=0.0001)

## E1 — statistics

### (conflict = ('high',))
| strategy | tau_causal | tau_contested | tauhat | info_retention |
|---|---|---|---|---|
| crdt_lww | 0.000±0.000 (n=30) | 0.500±0.731 (0.227,0.773) n=30 | 0.000±0.000 (0.000,0.000) n=30 | 1.000±0.000 (1.000,1.000) n=30 |
| crdt_pure | 0.000±0.000 (n=30) | 0.500±0.731 (0.227,0.773) n=30 | 0.000±0.000 (0.000,0.000) n=30 | 1.000±0.000 (1.000,1.000) n=30 |
| leader | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 1.000±0.000 (n=30) |
| lww | 0.000±0.000 (n=30) | 0.500±0.731 (0.227,0.773) n=30 | 0.000±0.000 (0.000,0.000) n=30 | 1.000±0.000 (1.000,1.000) n=30 |
| ranked_pairs | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 1.000±0.000 (n=30) |
| vc | 0.000±0.000 (n=30) | 0.500±0.731 (0.227,0.773) n=30 | 0.000±0.000 (0.000,0.000) n=30 | 1.000±0.000 (1.000,1.000) n=30 |

> Significant differences (p<0.05): crdt_lww vs leader (p=0.0024); crdt_lww vs ranked_pairs (p=0.0024); crdt_pure vs leader (p=0.0024); crdt_pure vs ranked_pairs (p=0.0024); leader vs lww (p=0.0024); leader vs vc (p=0.0024); lww vs ranked_pairs (p=0.0024); ranked_pairs vs vc (p=0.0024); Isomorphic (indistinguishable): crdt_lww ≡ crdt_pure; crdt_lww ≡ lww; crdt_lww ≡ vc; crdt_pure ≡ lww; crdt_pure ≡ vc; leader ≡ ranked_pairs; lww ≡ vc

### (conflict = ('low',))
| strategy | tau_causal | tau_contested | tauhat | info_retention |
|---|---|---|---|---|
| crdt_lww | 0.000±0.000 (n=30) | 0.500±0.820 (0.194,0.806) n=30 | 0.000±0.000 (0.000,0.000) n=30 | 1.000±0.000 (1.000,1.000) n=30 |
| crdt_pure | 0.000±0.000 (n=30) | 0.500±0.820 (0.194,0.806) n=30 | 0.000±0.000 (0.000,0.000) n=30 | 1.000±0.000 (1.000,1.000) n=30 |
| leader | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 1.000±0.000 (n=30) |
| lww | 0.000±0.000 (n=30) | 0.500±0.820 (0.194,0.806) n=30 | 0.000±0.000 (0.000,0.000) n=30 | 1.000±0.000 (1.000,1.000) n=30 |
| ranked_pairs | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 1.000±0.000 (n=30) |
| vc | 0.000±0.000 (n=30) | 0.500±0.820 (0.194,0.806) n=30 | 0.000±0.000 (0.000,0.000) n=30 | 1.000±0.000 (1.000,1.000) n=30 |

> Significant differences (p<0.05): crdt_lww vs leader (p=0.0040); crdt_lww vs ranked_pairs (p=0.0040); crdt_pure vs leader (p=0.0040); crdt_pure vs ranked_pairs (p=0.0040); leader vs lww (p=0.0040); leader vs vc (p=0.0040); lww vs ranked_pairs (p=0.0040); ranked_pairs vs vc (p=0.0040); Isomorphic (indistinguishable): crdt_lww ≡ crdt_pure; crdt_lww ≡ lww; crdt_lww ≡ vc; crdt_pure ≡ lww; crdt_pure ≡ vc; leader ≡ ranked_pairs; lww ≡ vc

## E2 — statistics

###

| strategy | ops_retained | auto_coverage | info_retention | tau_causal | tau_contested | semantic_validity | gini | time_ms |
|---|---|---|---|---|---|---|---|---|
| crdt_lww | 1.000±0.000 (n=30) | 1.000±0.000 (n=30) | 1.000±0.000 (1.000,1.000) n=30 | 0.000±0.000 (n=30) | 0.333±0.547 (0.129,0.537) n=30 | 0.822±0.187 (0.752,0.892) n=30 | 0.258±0.402 (0.108,0.408) n=30 | 0.043±0.010 (0.039,0.046) n=30 |
| crdt_pure | 1.000±0.000 (n=30) | 0.908±0.076 (0.880,0.937) n=30 | 1.000±0.000 (1.000,1.000) n=30 | 0.000±0.000 (n=30) | 0.333±0.547 (0.129,0.537) n=30 | 0.822±0.187 (0.752,0.892) n=30 | 0.258±0.402 (0.108,0.408) n=30 | 0.060±0.015 (0.054,0.065) n=30 |
| leader | 0.208±0.000 (0.208,0.208) n=30 | 1.000±0.000 (n=30) | 1.000±0.000 (n=30) | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 1.000±0.000 (n=30) | 0.000±0.000 (n=30) | 0.019±0.004 (0.017,0.020) n=30 |
| lww | 1.000±0.000 (n=30) | 1.000±0.000 (n=30) | 1.000±0.000 (1.000,1.000) n=30 | 0.000±0.000 (n=30) | 0.333±0.547 (0.129,0.537) n=30 | 0.822±0.187 (0.752,0.892) n=30 | 0.258±0.402 (0.108,0.408) n=30 | 0.059±0.013 (0.054,0.064) n=30 |
| ranked_pairs | 1.000±0.000 (n=30) | 1.000±0.000 (n=30) | 1.000±0.000 (n=30) | 0.000±0.000 (n=30) | 0.000±0.000 (n=30) | 0.828±0.185 (0.759,0.897) n=30 | 0.000±0.000 (n=30) | 1.272±0.206 (1.195,1.349) n=30 |
| vc | 1.000±0.000 (n=30) | 0.908±0.076 (0.880,0.937) n=30 | 1.000±0.000 (1.000,1.000) n=30 | 0.000±0.000 (n=30) | 0.333±0.547 (0.129,0.537) n=30 | 0.822±0.187 (0.752,0.892) n=30 | 0.258±0.402 (0.108,0.408) n=30 | 0.176±0.062 (0.152,0.199) n=30 |

> Significant differences (p<0.05): crdt_lww vs leader (p=0.0039); crdt_lww vs ranked_pairs (p=0.0039); crdt_pure vs leader (p=0.0039); crdt_pure vs ranked_pairs (p=0.0039); leader vs lww (p=0.0039); leader vs vc (p=0.0039); lww vs ranked_pairs (p=0.0039); ranked_pairs vs vc (p=0.0039); Isomorphic (indistinguishable): crdt_lww ≡ crdt_pure; crdt_lww ≡ lww; crdt_lww ≡ vc; crdt_pure ≡ lww; crdt_pure ≡ vc; leader ≡ ranked_pairs; lww ≡ vc

## E6a — statistics

### (minority_frac = (0.1,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.292±0.000 (n=15) | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |
| lww | 1.000±0.000 (n=15) | 1.000±0.000 (0.999,1.000) n=15 | 0.000±0.000 (0.000,0.001) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |

> Significant differences (p<0.05): leader vs lww (p=0.0062); lww vs ranked_pairs (p=0.0062); Isomorphic (indistinguishable): leader ≡ ranked_pairs

### (minority_frac = (0.2,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.250±0.000 (n=15) | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |
| lww | 1.000±0.000 (n=15) | 1.000±0.000 (0.999,1.000) n=15 | 0.000±0.000 (0.000,0.001) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |

> Significant differences (p<0.05): leader vs lww (p=0.0094); lww vs ranked_pairs (p=0.0094); Isomorphic (indistinguishable): leader ≡ ranked_pairs

### (minority_frac = (0.3,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.250±0.000 (n=15) | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |
| lww | 1.000±0.000 (n=15) | 1.000±0.000 (0.999,1.000) n=15 | 0.000±0.000 (0.000,0.001) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |

> Significant differences (p<0.05): leader vs lww (p=0.0030); lww vs ranked_pairs (p=0.0030); Isomorphic (indistinguishable): leader ≡ ranked_pairs

### (minority_frac = (0.4,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.208±0.000 (0.208,0.208) n=15 | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |
| lww | 1.000±0.000 (n=15) | 1.000±0.000 (1.000,1.000) n=15 | 0.000±0.000 (0.000,0.000) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |

> Significant differences (p<0.05): leader vs lww (p=0.0231); lww vs ranked_pairs (p=0.0231); Isomorphic (indistinguishable): leader ≡ ranked_pairs

### (minority_frac = (0.5,))
| strategy | ops_retained | info_retention | tauhat |
|---|---|---|---|
| leader | 0.167±0.000 (0.167,0.167) n=15 | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |
| lww | 1.000±0.000 (n=15) | 1.000±0.000 (1.000,1.000) n=15 | 0.000±0.000 (0.000,0.000) n=15 |
| ranked_pairs | 1.000±0.000 (n=15) | 1.000±0.000 (n=15) | 0.000±0.000 (n=15) |

> Significant differences (p<0.05): leader vs lww (p=0.0253); lww vs ranked_pairs (p=0.0253); Isomorphic (indistinguishable): leader ≡ ranked_pairs