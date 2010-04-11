VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Addin"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
Option Explicit

Private mMenuName As String
Private mClassName As String
Public Property Get MenuName() As String
    MenuName = mMenuName
End Property
Public Property Get ClassName() As String
    ClassName = mClassName
End Property

Friend Property Let ClassName(v As String)
    mClassName = v
End Property
Friend Property Let MenuName(v As String)
    mMenuName = v
End Property

