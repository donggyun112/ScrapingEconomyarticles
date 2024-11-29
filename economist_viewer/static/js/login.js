const LoginForm = () => {
	const [credentials, setCredentials] = React.useState({
	  email: '',
	  password: '',
	});
	const [loading, setLoading] = React.useState(false);
	const [error, setError] = React.useState('');
  
	const handleChange = (e) => {
	  setCredentials({
		...credentials,
		[e.target.name]: e.target.value
	  });
	};
  
	const handleSubmit = async (e) => {
	  e.preventDefault();
	  setLoading(true);
	  setError('');
  
	  try {
		const response = await fetch('/api/login', {
		  method: 'POST',
		  headers: {
			'Content-Type': 'application/json',
		  },
		  body: JSON.stringify(credentials)
		});
  
		const data = await response.json();
  
		if (!response.ok) {
		  throw new Error(data.error || '로그인에 실패했습니다');
		}
  
		window.location.href = '/';
	  } catch (err) {
		setError(err.message);
	  } finally {
		setLoading(false);
	  }
	};
  
	return React.createElement('div', {
	  className: 'min-h-screen flex items-center justify-center bg-gray-50'
	},
	  React.createElement('div', {
		className: 'max-w-md w-full space-y-8 p-8 bg-white rounded-lg shadow-lg'
	  },
		React.createElement('div', null,
		  React.createElement('h2', {
			className: 'text-center text-3xl font-bold text-gray-900'
		  }, '로그인'),
		  React.createElement('p', {
			className: 'mt-2 text-center text-sm text-gray-600'
		  }, 'Economist 계정으로 로그인하세요')
		),
		React.createElement('form', {
		  className: 'mt-8 space-y-6',
		  onSubmit: handleSubmit
		},
		  React.createElement('div', {
			className: 'rounded-md shadow-sm space-y-4'
		  },
			React.createElement('div', null,
			  React.createElement('input', {
				id: 'email',
				name: 'email',
				type: 'email',
				required: true,
				className: 'appearance-none rounded relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500',
				placeholder: '이메일',
				value: credentials.email,
				onChange: handleChange
			  })
			),
			React.createElement('div', null,
			  React.createElement('input', {
				id: 'password',
				name: 'password',
				type: 'password',
				required: true,
				className: 'appearance-none rounded relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500',
				placeholder: '비밀번호',
				value: credentials.password,
				onChange: handleChange
			  })
			)
		  ),
		  error && React.createElement('div', {
			className: 'text-red-500 text-sm text-center'
		  }, error),
		  React.createElement('div', null,
			React.createElement('button', {
			  type: 'submit',
			  disabled: loading,
			  className: 'group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50'
			}, loading ? '로그인 중...' : '로그인')
		  )
		)
	  )
	);
  };
  
  ReactDOM.render(
	React.createElement(LoginForm),
	document.getElementById('root')
  );