VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Properties"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
Attribute VB_Ext_KEY = "SavedWithClassBuilder6" ,"Yes"
Attribute VB_Ext_KEY = "Collection" ,"Property"
Attribute VB_Ext_KEY = "Member0" ,"Property"
Attribute VB_Ext_KEY = "Top_Level" ,"Yes"
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit

'local variable to hold collection
Private mCol As Collection
Private WithEvents mParentContainer As Container
Attribute mParentContainer.VB_VarHelpID = -1

Private mParent As Container

Private mstrName As String

Friend Property Set ParentContainer(v As Container)
    Set mParent = v
End Property

Public Property Get PropertyGroup() As PropertyGroup
    Set PropertyGroup = mParent.GetParent
End Property

Public Property Get Name() As String
    Name = mstrName
End Property

Friend Property Let Name(v As String)
    mstrName = v
End Property

Public Function Add(Name As String, Value As Variant, Optional PropertyType As enPropertyTypes = ptString, Optional Locked As Boolean = False) As Property
    'create a new object
    Dim objNewMember As Property
    Set objNewMember = New Property
    Set objNewMember.ParentContainer = mParentContainer

    'set the properties passed into the method
    With objNewMember
        If IsObject(Value) Then
            Set .Value = Value
        Else
            .Value = Value
        End If
        .Name = Name
        .PropertyType = PropertyType
        .Locked = Locked
    End With
    
    mCol.Add objNewMember, UCase$(Name)

    'return the object created
    Set Add = objNewMember
    Set objNewMember = Nothing
    
End Function

Public Sub Clear()
    Set mCol = New Collection
End Sub

Public Property Get Item(vntIndexKey As Variant) As Property
Attribute Item.VB_UserMemId = 0
    'used when referencing an element in the collection
    'vntIndexKey contains either the Index or Key to the collection,
    'this is why it is declared as a Variant
    'Syntax: Set foo = x.Item(xyz) or Set foo = x.Item(5)
    Select Case VarType(vntIndexKey)
        Case VbVarType.vbInteger, VbVarType.vbLong
            
            Set Item = mCol(vntIndexKey)
        Case Else
            Set Item = mCol(UCase$(vntIndexKey))
    End Select
End Property



Public Property Get Count() As Long
    'used when retrieving the number of elements in the
    'collection. Syntax: Debug.Print x.Count
    Count = mCol.Count
End Property


Public Sub Remove(vntIndexKey As Variant)
    'used when removing an element from the collection
    'vntIndexKey contains either the Index or Key, which is why
    'it is declared as a Variant
    'Syntax: x.Remove(xyz)
    If VarType(vntIndexKey) = vbString Then
        mCol.Remove UCase$(vntIndexKey)
    Else
        mCol.Remove vntIndexKey
    End If
End Sub


Public Property Get NewEnum() As IUnknown
Attribute NewEnum.VB_UserMemId = -4
Attribute NewEnum.VB_MemberFlags = "40"
    'this property allows you to enumerate
    'this collection with the For...Each syntax
    Set NewEnum = mCol.[_NewEnum]
End Property


Private Sub Class_Initialize()
    'creates the collection when this class is created
    Set mCol = New Collection
    Set mParentContainer = New Container
End Sub


Private Sub Class_Terminate()
    'destroys collection when this class is terminated
    Set mCol = Nothing
End Sub

Public Function Exists(PropertyName As String) As Boolean
    On Error Resume Next
    Dim oProp As Property
    Set oProp = mCol(UCase$(PropertyName))
    If Err.Number <> 0 Then
        Exists = False
    Else
        Exists = True
    End If
    Err.Clear
End Function

Private Sub mParentContainer_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub


