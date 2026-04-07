# Implementation Templates Part 2: Risk Models and Execution

---

## PART 3 CONTINUATION: MEAN REVERSION IMPROVEMENTS

### 3.3 Kalman Filtering for Dynamic Mean Estimation

```python
# File: src/strategies/kalman_filter_mean.py

import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional
from enum import Enum

@dataclass
class KalmanState:
    """Kalman filter state"""
    mean_estimate: float
    mean_uncertainty: float
    observation_noise: float  # R
    process_noise: float  # Q
    kalman_gain: float
    log_likelihood: float

class KalmanMeanFilter:
    """
    Kalman filter for dynamic mean estimation

    State: μ_t (true mean)
    Observation: y_t (price)

    State equation:    μ_t = μ_{t-1} + w_t,   w_t ~ N(0, Q)
    Observation eq:    y_t = μ_t + v_t,       v_t ~ N(0, R)
    """

    def __init__(self,
                 initial_mean: float,
                 initial_uncertainty: float = 1.0,
                 process_noise: float = 0.01,
                 observation_noise: float = 1.0):
        """
        Initialize Kalman filter

        Args:
            initial_mean: Initial estimate of mean
            initial_uncertainty: Initial uncertainty P_0
            process_noise: Q (mean drift noise)
            observation_noise: R (price observation noise)
        """
        self.mu = initial_mean
        self.P = initial_uncertainty
        self.Q = process_noise
        self.R = observation_noise

        # History for EM learning
        self.innovation_history = []
        self.state_history = []

    def predict(self) -> Tuple[float, float]:
        """
        Prediction step: predict next mean estimate

        μ̂_{t|t-1} = μ̂_{t-1|t-1}
        P_{t|t-1} = P_{t-1|t-1} + Q

        Returns:
            (predicted_mean, predicted_uncertainty)
        """
        mu_predict = self.mu
        P_predict = self.P + self.Q

        return mu_predict, P_predict

    def update(self, observation: float) -> KalmanState:
        """
        Update step: incorporate new price observation

        K_t = P_{t|t-1} / (P_{t|t-1} + R)
        μ̂_{t|t} = μ̂_{t|t-1} + K_t * (y_t - μ̂_{t|t-1})
        P_{t|t} = (1 - K_t) * P_{t|t-1}

        Args:
            observation: Observed price

        Returns:
            KalmanState with updated estimates
        """
        # Prediction
        mu_predict, P_predict = self.predict()

        # Kalman gain
        K = P_predict / (P_predict + self.R)

        # Innovation (prediction error)
        innovation = observation - mu_predict

        # Update state
        self.mu = mu_predict + K * innovation
        self.P = (1 - K) * P_predict

        # Log-likelihood for this observation
        ll = -0.5 * np.log(2 * np.pi * (P_predict + self.R)) - \
             0.5 * innovation**2 / (P_predict + self.R)

        # Track for EM
        self.innovation_history.append(innovation)
        self.state_history.append(self.mu)

        return KalmanState(
            mean_estimate=self.mu,
            mean_uncertainty=self.P,
            observation_noise=self.R,
            process_noise=self.Q,
            kalman_gain=K,
            log_likelihood=ll
        )

    def learn_noise_parameters(self) -> Tuple[float, float]:
        """
        EM algorithm to learn Q and R from innovations

        E-step: Calculate expected values using Kalman smoother
        M-step: Update Q and R estimates

        Returns:
            (estimated_Q, estimated_R)
        """
        if len(self.innovation_history) < 10:
            return self.Q, self.R

        innovations = np.array(self.innovation_history)

        # Simple EM: estimate R from innovation variance
        # Better method would use Kalman smoother
        R_est = np.var(innovations)

        # Q estimation: changes in smoothed states
        if len(self.state_history) > 2:
            state_diffs = np.diff(self.state_history)
            Q_est = np.var(state_diffs)
        else:
            Q_est = self.Q

        # Smooth estimates with prior to prevent instability
        alpha = 0.1  # Learning rate
        self.Q = (1 - alpha) * self.Q + alpha * max(Q_est, 1e-6)
        self.R = (1 - alpha) * self.R + alpha * max(R_est, 1e-2)

        return self.Q, self.R

    def get_dynamic_zscore(self, current_price: float) -> float:
        """
        Get Z-score based on dynamic mean

        z = (price - μ_dynamic) / √P_uncertainty
        """
        if self.P < 1e-8:
            return 0.0

        z_score = (current_price - self.mu) / np.sqrt(self.P)
        return z_score

    def batch_filter(self, prices: np.ndarray) -> np.ndarray:
        """
        Apply Kalman filter to entire price series

        Returns:
            Array of filtered mean estimates
        """
        prices = np.asarray(prices).flatten()
        means = np.zeros(len(prices))

        for i, price in enumerate(prices):
            state = self.update(price)
            means[i] = state.mean_estimate

            # Periodically learn parameters
            if (i + 1) % 50 == 0:
                self.learn_noise_parameters()

        return means

# Usage example:
kf = KalmanMeanFilter(
    initial_mean=50.0,
    initial_uncertainty=1.0,
    process_noise=0.01,
    observation_noise=4.0
)

prices = np.array([50, 49.5, 50.2, 49.8, 50.1, 49.9, ...])

for price in prices:
    state = kf.update(price)
    z_score = kf.get_dynamic_zscore(price)
    print(f"Price: {price:.2f}, Mean: {state.mean_estimate:.2f}, Z: {z_score:.2f}")

# Learn parameters from data
Q_learned, R_learned = kf.learn_noise_parameters()
print(f"Learned Q: {Q_learned:.6f}, R: {R_learned:.4f}")
```

---

## PART 4: RISK PREDICTION MODELS

### 4.1 GARCH Model for Volatility Forecasting

```python
# File: src/risk/garch_volatility.py

import numpy as np
from scipy.optimize import minimize
from dataclasses import dataclass
from typing import Tuple, Dict

@dataclass
class GARCHMetrics:
    """GARCH model results"""
    omega: float
    alpha: float
    beta: float
    log_likelihood: float
    current_variance: float
    one_step_ahead_variance: float
    var_95: float
    var_99: float

class GARCHModel:
    """
    GARCH(1,1) volatility model

    σ²_t = ω + α*ε²_{t-1} + β*σ²_{t-1}
    """

    def __init__(self):
        self.omega = None
        self.alpha = None
        self.beta = None
        self.variance_history = []
        self.return_history = []

    def _garch_likelihood(self,
                        params: np.ndarray,
                        returns: np.ndarray) -> float:
        """
        Negative log-likelihood for GARCH model
        """
        omega, alpha, beta = params

        # Parameter constraints
        if omega <= 0 or alpha <= 0 or beta <= 0:
            return 1e10
        if alpha + beta >= 1.0:  # Non-stationarity
            return 1e10

        n = len(returns)
        ll = 0.0

        # Initialize variance
        sigma2 = np.var(returns)

        for t in range(1, n):
            # GARCH equation
            sigma2 = omega + alpha * returns[t-1]**2 + beta * sigma2

            if sigma2 <= 0:
                return 1e10

            # Log-likelihood contribution
            ll -= 0.5 * np.log(2 * np.pi * sigma2) - 0.5 * returns[t]**2 / sigma2

        return -ll  # Return negative for minimization

    def fit(self, returns: np.ndarray, learning_rate: float = 0.1):
        """
        Fit GARCH model to return series using MLE

        Args:
            returns: Array of returns
            learning_rate: For online learning (0 = no update)
        """
        returns = np.asarray(returns).flatten()
        self.return_history.extend(returns)

        # Initial parameters (method of moments)
        mean_return = np.mean(returns)
        centered_returns = returns - mean_return

        omega_init = np.var(centered_returns) * 0.0001
        alpha_init = 0.10
        beta_init = 0.85

        # Optimize
        result = minimize(
            self._garch_likelihood,
            x0=[omega_init, alpha_init, beta_init],
            args=(returns,),
            method='SLSQP',
            bounds=[(1e-6, 1e-3), (0.01, 0.30), (0.50, 0.99)]
        )

        if result.success:
            new_params = result.x
        else:
            new_params = np.array([omega_init, alpha_init, beta_init])

        # Online update if we have previous estimates
        if self.omega is not None and learning_rate > 0:
            self.omega = (1 - learning_rate) * self.omega + learning_rate * new_params[0]
            self.alpha = (1 - learning_rate) * self.alpha + learning_rate * new_params[1]
            self.beta = (1 - learning_rate) * self.beta + learning_rate * new_params[2]
        else:
            self.omega, self.alpha, self.beta = new_params

        # Recalculate variance path
        self._update_variance_history(returns)

        return GARCHMetrics(
            omega=self.omega,
            alpha=self.alpha,
            beta=self.beta,
            log_likelihood=-result.fun if result.success else -self._garch_likelihood(new_params, returns),
            current_variance=self.variance_history[-1] if self.variance_history else np.var(returns),
            one_step_ahead_variance=self._forecast_variance(1),
            var_95=None,  # Calculated below
            var_99=None
        )

    def _update_variance_history(self, returns: np.ndarray):
        """Recalculate conditional variance path"""
        self.variance_history = []
        sigma2 = np.var(returns)

        for r in returns:
            sigma2 = self.omega + self.alpha * r**2 + self.beta * sigma2
            self.variance_history.append(sigma2)

    def _forecast_variance(self, h: int) -> float:
        """
        Forecast variance h steps ahead

        σ²_{t+h|t} = ω*(1-(α+β)^h)/(1-α-β) + (α+β)^h*σ²_t

        For h=1: σ²_{t+1} = ω + α*ε²_t + β*σ²_t
        """
        if self.omega is None or len(self.variance_history) == 0:
            return 0.01

        current_sigma2 = self.variance_history[-1]
        persistence = self.alpha + self.beta

        if abs(persistence) < 1e-6:
            return self.omega

        long_run_variance = self.omega / (1 - persistence)
        forecast = (long_run_variance * (1 - persistence**h) +
                   persistence**h * current_sigma2)

        return forecast

    def forecast_volatility(self, h: int = 1) -> float:
        """
        Forecast volatility h steps ahead

        Returns std dev, not variance
        """
        var_forecast = self._forecast_variance(h)
        return np.sqrt(max(var_forecast, 0))

    def get_position_adjustment(self, current_price: float, position_base: float) -> float:
        """
        Adjust position size based on GARCH forecast

        Lower volatility forecast = larger position
        """
        vol_forecast_1 = self.forecast_volatility(1)
        vol_historical = np.std(self.return_history[-50:]) if len(self.return_history) >= 50 else 0.01

        if vol_historical > 0:
            vol_ratio = vol_historical / max(vol_forecast_1, 0.001)
        else:
            vol_ratio = 1.0

        # Smooth adjustment (exponential damping)
        adjustment = np.exp(-max(0, vol_forecast_1 - vol_historical))

        return position_base * adjustment

# Usage example:
garch = GARCHModel()

returns = np.random.normal(0.0005, 0.02, 500)  # Simulated returns
metrics = garch.fit(returns)

print(f"ω: {metrics.omega:.6f}")
print(f"α: {metrics.alpha:.4f}")
print(f"β: {metrics.beta:.4f}")
print(f"Current variance: {metrics.current_variance:.6f}")
print(f"1-step ahead vol: {np.sqrt(metrics.one_step_ahead_variance):.4f}")

# Forecast volatility
vol_5step = garch.forecast_volatility(5)
print(f"5-step volatility forecast: {vol_5step:.4f}")

# Adjust position size
pos_adjusted = garch.get_position_adjustment(50.0, 0.05)
print(f"Adjusted position size: {pos_adjusted:.4%}")
```

### 4.2 Extreme Value Theory for VaR Estimation

```python
# File: src/risk/extreme_value_theory.py

import numpy as np
from scipy.optimize import minimize
from scipy.special import gamma
from dataclasses import dataclass
from typing import Tuple

@dataclass
class EVTMetrics:
    """Extreme Value Theory results"""
    shape_parameter: float  # ξ (xi)
    scale_parameter: float  # β
    threshold: float
    num_exceedances: int
    var_95: float
    var_99: float
    var_99_9: float
    expected_shortfall_95: float
    tail_ratio: float  # Normal VaR vs EVT VaR

class ExtremeValueCalculator:
    """
    Peak-Over-Threshold (POT) method using Generalized Pareto Distribution

    GPD: P(X > u + x | X > u) = (1 + ξ*x/β)^(-1/ξ)
    """

    def __init__(self, threshold_percentile: float = 90.0):
        self.threshold_percentile = threshold_percentile
        self.threshold = None
        self.shape = None  # ξ
        self.scale = None  # β

    def _gpd_loglikelihood(self, params, exceedances):
        """
        Log-likelihood for GPD parameters
        """
        xi, beta = params

        if beta <= 0 or xi <= -1:
            return 1e10

        x = exceedances
        ll = -len(x) * np.log(beta) - (1 + 1/xi) * np.sum(np.log(1 + xi * x / beta))

        # Penalize near boundary
        if xi > 0.9:
            ll += 100 * (xi - 0.9)**2

        return -ll  # Return negative for minimization

    def _hill_estimator(self, exceedances: np.ndarray) -> float:
        """
        Hill estimator for shape parameter ξ

        ξ = 1 + (1/m) * Σ log(X_i / u)
        """
        if len(exceedances) < 2:
            return 0.2

        mean_log_ratio = np.mean(np.log(exceedances))
        return 1 + mean_log_ratio

    def fit(self, returns: np.ndarray):
        """
        Fit EVT model to tail of return distribution
        """
        returns = np.asarray(returns).flatten()

        # Set threshold at percentile
        self.threshold = np.percentile(returns, self.threshold_percentile)

        # Extract exceedances
        exceedances = returns[returns > self.threshold] - self.threshold

        if len(exceedances) < 5:
            self.shape = 0.2
            self.scale = np.std(returns)
            return

        # Initial estimate using Hill method
        xi_init = self._hill_estimator(exceedances)
        beta_init = np.mean(exceedances)

        # MLE optimization
        result = minimize(
            self._gpd_loglikelihood,
            x0=[xi_init, beta_init],
            args=(exceedances,),
            method='SLSQP',
            bounds=[(0.0, 0.9), (0.001, 100)]
        )

        if result.success:
            self.shape, self.scale = result.x
        else:
            self.shape, self.scale = xi_init, beta_init

    def calculate_var(self, confidence_level: float, tail_prob: float = None) -> float:
        """
        Calculate VaR using EVT

        VaR_p = u + (β/ξ) * [(n/m * (1-p))^(-ξ) - 1]

        Args:
            confidence_level: Confidence level (0.95, 0.99, 0.999)
            tail_prob: Probability of exceeding threshold (auto-calculated if None)
        """
        if self.shape is None or self.scale is None:
            return 0.0

        if tail_prob is None:
            # Estimate empirically
            tail_prob = (100 - self.threshold_percentile) / 100

        p_u = tail_prob
        p = 1 - confidence_level

        # VaR formula
        if abs(self.shape) < 1e-6:
            # Exponential case (ξ → 0)
            var = self.threshold - self.scale * np.log(p / p_u)
        else:
            # General GPD case
            var = self.threshold + (self.scale / self.shape) * \
                  (np.power(p / p_u, -self.shape) - 1)

        return var

    def calculate_expected_shortfall(self, confidence_level: float) -> float:
        """
        Expected Shortfall (Conditional Value at Risk)

        ES_p = VaR_p / (1 - ξ) + (β - ξ*u) / (1 - ξ)
        """
        if self.shape is None or self.shape >= 1.0:
            return self.calculate_var(confidence_level)

        var = self.calculate_var(confidence_level)

        es = (var + self.scale - self.shape * self.threshold) / (1 - self.shape)

        return es

    def get_evt_metrics(self, returns: np.ndarray) -> EVTMetrics:
        """
        Comprehensive EVT analysis
        """
        self.fit(returns)

        var_95 = self.calculate_var(0.95)
        var_99 = self.calculate_var(0.99)
        var_99_9 = self.calculate_var(0.999)

        es_95 = self.calculate_expected_shortfall(0.95)

        # Compare to normal distribution VaR
        normal_mean = np.mean(returns)
        normal_std = np.std(returns)
        normal_var_99 = normal_mean - 2.33 * normal_std

        tail_ratio = var_99 / normal_var_99

        num_exc = np.sum(returns > self.threshold)

        return EVTMetrics(
            shape_parameter=self.shape,
            scale_parameter=self.scale,
            threshold=self.threshold,
            num_exceedances=num_exc,
            var_95=var_95,
            var_99=var_99,
            var_99_9=var_99_9,
            expected_shortfall_95=es_95,
            tail_ratio=tail_ratio
        )

# Usage example:
evt = ExtremeValueCalculator(threshold_percentile=90)

returns = np.random.normal(0, 0.02, 1000)
# Add fat tail event
returns = np.append(returns, np.random.pareto(2.0, 50) * 0.05)

metrics = evt.get_evt_metrics(returns)

print(f"Shape (ξ): {metrics.shape_parameter:.4f} (fat tail indicator)")
print(f"VaR 99%: {metrics.var_99:.4f}")
print(f"VaR 99.9%: {metrics.var_99_9:.4f}")
print(f"Expected Shortfall: {metrics.expected_shortfall_95:.4f}")
print(f"Tail ratio (EVT/Normal): {metrics.tail_ratio:.2f}x")
```

### 4.3 Dynamic Correlation Matrix (DCC-GARCH)

```python
# File: src/risk/dynamic_correlation.py

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class DCCMetrics:
    """Dynamic correlation results"""
    correlation_matrix: np.ndarray
    unconditional_correlation: np.ndarray
    dcc_a: float  # scalar parameter a
    dcc_b: float  # scalar parameter b
    average_correlation: float
    diversification_ratio: float
    portfolio_variance: float

class DynamicConditionalCorrelation:
    """
    DCC-GARCH model for time-varying correlations

    Q_t = (1 - a - b) * Q̄ + a * z_{t-1} * z_{t-1}' + b * Q_{t-1}
    """

    def __init__(self, num_assets: int):
        self.num_assets = num_assets
        self.dcc_a = 0.02
        self.dcc_b = 0.94
        self.Q_bar = np.eye(num_assets)  # Unconditional correlation
        self.Q_t = np.eye(num_assets)    # Current Q
        self.correlation_history = []

    def calculate_standardized_residuals(self,
                                         returns: np.ndarray) -> np.ndarray:
        """
        Calculate standardized residuals from univariate GARCH

        z_t = r_t / σ_t

        Simplified: use rolling std
        """
        returns = np.asarray(returns)

        window = 20
        std_series = np.array([
            np.std(returns[:, i][max(0, j-window):j] if j > 0 else returns[:, i][:j])
            if j > 0 else np.std(returns[0:1, i])
            for i in range(returns.shape[1])
            for j in range(returns.shape[0])
        ])

        # Reshape and avoid division by zero
        std_series = std_series.reshape(returns.shape)
        std_series = np.maximum(std_series, 0.001)

        z = returns / std_series
        return z

    def update_unconditional_correlation(self, z: np.ndarray):
        """
        Update unconditional correlation matrix Q̄

        Q̄ = E[z_t * z_t']
        """
        self.Q_bar = z.T @ z / len(z)
        # Normalize to correlation
        diag_inv = 1.0 / np.sqrt(np.diag(self.Q_bar))
        self.Q_bar = np.diag(diag_inv) @ self.Q_bar @ np.diag(diag_inv)

    def update_Q_matrix(self, z_t: np.ndarray):
        """
        Update Q matrix (pseudo-correlation)

        Q_t = (1 - a - b) * Q̄ + a * z_{t-1} * z_{t-1}' + b * Q_{t-1}
        """
        z_outer = np.outer(z_t, z_t)

        Q_new = ((1 - self.dcc_a - self.dcc_b) * self.Q_bar +
                self.dcc_a * z_outer +
                self.dcc_b * self.Q_t)

        self.Q_t = Q_new

    def get_correlation_matrix(self) -> np.ndarray:
        """
        Get current correlation matrix from Q

        R_t = D_t^{-1} * Q_t * D_t^{-1}
        where D_t = sqrt(diag(Q_t))
        """
        diag_sqrt = np.sqrt(np.abs(np.diag(self.Q_t)))
        diag_sqrt = np.maximum(diag_sqrt, 0.001)  # Avoid division by zero

        D_inv = np.diag(1.0 / diag_sqrt)
        R_t = D_inv @ self.Q_t @ D_inv

        # Ensure valid correlation ([-1, 1])
        R_t = np.clip(R_t, -1, 1)

        return R_t

    def get_covariance_matrix(self,
                             volatilities: np.ndarray) -> np.ndarray:
        """
        Construct covariance matrix H_t = D_t * R_t * D_t

        Args:
            volatilities: Array of conditional volatilities
        """
        R_t = self.get_correlation_matrix()
        D_t = np.diag(volatilities)
        H_t = D_t @ R_t @ D_t

        return H_t

    def calculate_portfolio_variance(self,
                                    weights: np.ndarray,
                                    volatilities: np.ndarray) -> float:
        """
        Calculate portfolio variance

        σ²_p = w' * H_t * w
        """
        H_t = self.get_covariance_matrix(volatilities)
        var_p = weights @ H_t @ weights

        return var_p

    def calculate_diversification_ratio(self,
                                       weights: np.ndarray,
                                       volatilities: np.ndarray) -> float:
        """
        Diversification Ratio = Σ|w_i|*σ_i / σ_portfolio

        Higher ratio = better diversification
        Max = n (equal weight, perfect correlation=0)
        Min = 1 (one asset, or perfect correlation=1)
        """
        numerator = np.sum(np.abs(weights) * volatilities)
        portfolio_vol = np.sqrt(self.calculate_portfolio_variance(weights, volatilities))

        if portfolio_vol < 1e-8:
            return 1.0

        dr = numerator / portfolio_vol
        return dr

    def fit(self, returns: np.ndarray, a_init: float = 0.02, b_init: float = 0.94):
        """
        Fit DCC parameters (simplified)

        In practice, would use maximum likelihood
        """
        z = self.calculate_standardized_residuals(returns)
        self.update_unconditional_correlation(z)

        self.dcc_a = a_init
        self.dcc_b = b_init

        # Apply filter
        for t in range(len(z)):
            self.update_Q_matrix(z[t])
            self.correlation_history.append(self.get_correlation_matrix().copy())

    def get_dcc_metrics(self,
                       returns: np.ndarray,
                       weights: np.ndarray,
                       volatilities: np.ndarray) -> DCCMetrics:
        """
        Comprehensive DCC analysis
        """
        self.fit(returns)

        R_current = self.get_correlation_matrix()
        portfolio_var = self.calculate_portfolio_variance(weights, volatilities)
        diversification_ratio = self.calculate_diversification_ratio(weights, volatilities)

        # Average correlation (excluding diagonal)
        mask = ~np.eye(self.num_assets, dtype=bool)
        avg_corr = R_current[mask].mean()

        return DCCMetrics(
            correlation_matrix=R_current,
            unconditional_correlation=self.Q_bar,
            dcc_a=self.dcc_a,
            dcc_b=self.dcc_b,
            average_correlation=avg_corr,
            diversification_ratio=diversification_ratio,
            portfolio_variance=portfolio_var
        )

# Usage example:
returns = np.random.randn(500, 3) * 0.02  # 3 assets, 500 days

dcc = DynamicConditionalCorrelation(num_assets=3)
dcc.fit(returns)

weights = np.array([0.33, 0.33, 0.34])
volatilities = np.array([0.015, 0.012, 0.018])

metrics = dcc.get_dcc_metrics(returns, weights, volatilities)

print(f"Current correlation matrix:")
print(metrics.correlation_matrix)
print(f"\nAverage correlation: {metrics.average_correlation:.3f}")
print(f"Diversification ratio: {metrics.diversification_ratio:.2f}")
print(f"Portfolio variance: {metrics.portfolio_variance:.6f}")
```

---

## PART 5: EXECUTION OPTIMIZATION

### 5.1 Almgren-Chriss Optimal Execution

```python
# File: src/execution/almgren_chriss.py

import numpy as np
from scipy.integrate import odeint
from dataclasses import dataclass
from typing import Tuple, List

@dataclass
class ExecutionMetrics:
    """Optimal execution results"""
    optimal_velocity: float
    execution_cost_bps: float
    permanent_impact: float
    temporary_impact: float
    recommended_execution_time: float
    position_adjusted: float

class AlmgrenChrissExecutor:
    """
    Almgren-Chriss framework for optimal execution

    Minimizes: Cost = Σ[permanent_impact + temporary_impact] + λ*variance

    Trade-off: Fast execution (high impact) vs slow execution (timing risk)
    """

    def __init__(self,
                 permanent_impact_coef: float = 0.0002,
                 temporary_impact_coef: float = 0.0003,
                 risk_aversion: float = 0.001):
        """
        Args:
            permanent_impact_coef: Γ (gamma)
            temporary_impact_coef: η (eta)
            risk_aversion: λ (lambda)
        """
        self.gamma = permanent_impact_coef  # Permanent impact
        self.eta = temporary_impact_coef    # Temporary impact
        self.lambda_risk = risk_aversion    # Risk aversion

    def calculate_optimal_velocity(self,
                                  total_volume: float,
                                  horizon_bars: int) -> float:
        """
        Calculate optimal execution velocity

        Minimizing impact without risk:
        v* = sqrt(Γ / η) * (V / T)

        With risk aversion:
        v_optimal = (V / T) * (1 / (1 + λ*T/(2*η)))
        """
        # Simple case: optimal velocity scaling
        if horizon_bars <= 0:
            return total_volume

        base_velocity = total_volume / horizon_bars

        # Adjust for risk aversion
        risk_term = self.lambda_risk * horizon_bars / (2 * self.eta)
        velocity_adjusted = base_velocity / (1 + risk_term)

        return velocity_adjusted

    def calculate_execution_cost(self,
                                total_volume: float,
                                horizon_bars: int) -> Tuple[float, float, float]:
        """
        Calculate total execution cost

        Cost = permanent_impact + temporary_impact

        Returns:
            (total_cost_bps, permanent_impact, temporary_impact)
        """
        if horizon_bars <= 0:
            horizon_bars = 1

        avg_velocity = total_volume / horizon_bars

        # Permanent impact: price drift from trading
        permanent_impact = self.gamma * total_volume / 2

        # Temporary impact: V-shaped cost around midpoint
        temporary_impact = self.eta * avg_velocity / 2

        # Total cost in basis points
        # Assuming price ~$0.50 for prediction market
        price_scale = 0.50
        total_cost_bps = (permanent_impact + temporary_impact) / price_scale * 10000

        return total_cost_bps, permanent_impact, temporary_impact

    def get_execution_path(self,
                          total_volume: float,
                          horizon_bars: int) -> np.ndarray:
        """
        Generate optimal execution path

        Optimal path balances:
        - Executing early to minimize timing risk
        - Executing slowly to minimize market impact

        Returns:
            Array of volumes to execute each bar
        """
        if horizon_bars <= 0:
            return np.array([total_volume])

        # Linear VWAP as baseline
        linear_path = np.full(horizon_bars, total_volume / horizon_bars)

        # Adjust with risk aversion
        # Under higher risk aversion, front-load execution
        front_load = min(0.4, self.lambda_risk * 100)  # Maximum 40% front-load

        path = linear_path.copy()
        path[0] += total_volume * front_load
        path[-1] -= total_volume * front_load

        # Normalize
        path = path * total_volume / np.sum(path)

        return path

    def calculate_market_impact(self,
                               total_volume: float,
                               price: float) -> float:
        """
        Calculate expected market impact in price units

        impact = Γ * V + η * V
        """
        impact = (self.gamma + self.eta) * total_volume
        return impact

    def get_optimal_position(self,
                            target_position: float,
                            current_price: float,
                            available_time_bars: int) -> ExecutionMetrics:
        """
        Calculate optimal position accounting for execution costs

        Adjusted position = target - expected_slippage
        """
        execution_cost_bps, perm_impact, temp_impact = self.calculate_execution_cost(
            target_position, available_time_bars
        )

        # Convert cost to position adjustment
        slippage_pct = execution_cost_bps / 10000
        position_adjusted = target_position * (1 - slippage_pct)

        optimal_velocity = self.calculate_optimal_velocity(target_position, available_time_bars)

        return ExecutionMetrics(
            optimal_velocity=optimal_velocity,
            execution_cost_bps=execution_cost_bps,
            permanent_impact=perm_impact,
            temporary_impact=temp_impact,
            recommended_execution_time=available_time_bars,
            position_adjusted=position_adjusted
        )

# Usage example:
executor = AlmgrenChrissExecutor(
    permanent_impact_coef=0.0002,
    temporary_impact_coef=0.0003,
    risk_aversion=0.001
)

# Want to execute 50,000 contracts
metrics = executor.get_optimal_position(
    target_position=50000,
    current_price=0.50,
    available_time_bars=10
)

print(f"Optimal velocity: {metrics.optimal_velocity:.0f} contracts/bar")
print(f"Execution cost: {metrics.execution_cost_bps:.1f} bps")
print(f"Permanent impact: {metrics.permanent_impact:.4f}")
print(f"Adjusted position: {metrics.position_adjusted:.0f}")

# Get execution path
path = executor.get_execution_path(50000, 10)
print(f"Execution path: {path}")
print(f"Cumulative: {np.cumsum(path)}")
```

---

## Integration Checklist

To integrate these improvements into the existing codebase:

1. **Position Sizing**: Replace current Kelly in `src/risk/kelly_criterion.py`
2. **Signal Quality**: Enhance signals in strategy files with IR and calibration
3. **Mean Reversion**: Integrate ADF/MLE/Kalman into `src/strategies/mean_reversion_detector.py`
4. **Risk Models**: Add GARCH/EVT/DCC to `src/risk/dynamic_risk_manager.py`
5. **Execution**: Implement in `src/backtesting/execution_simulator.py`

**Testing Priority**:
- Unit tests for each module
- Integration tests with backtesting engine
- Walk-forward validation on out-of-sample data
- Stress testing with historical crisis periods

**Expected Timeline**: 2-4 weeks to full implementation with proper testing
